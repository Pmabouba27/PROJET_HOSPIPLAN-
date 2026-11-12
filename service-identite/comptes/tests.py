"""Tests de service-identite : connexion, JWT, rôles, isolation des établissements,
jetons de service et format d'erreur (CONTRATS §2-4)."""
import json
from datetime import datetime, timedelta, timezone

import jwt
from django.conf import settings
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase

from .models import Etablissement, Utilisateur

PWD = "Motdepasse-Test-2026"
Role = Utilisateur.Role
CLIENTS = json.dumps({"service-planning": {"secret": "s3cret-planning", "scope": ["personnel:read"]}})


def decode(token, audience="hospiplan-api"):
    return jwt.decode(token, settings.JWT_PUBLIC_KEY, algorithms=["RS256"],
                      audience=audience, issuer="hospiplan-identite")


class Base(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.etab = Etablissement.objects.create(nom="CHU A", siret="11111111111111", ville="Lyon",
                                                plan="STANDARD")
        cls.autre = Etablissement.objects.create(nom="CH B", siret="22222222222222", ville="Nantes")
        mk = Utilisateur.objects.create_user
        cls.superadmin = Utilisateur.objects.create_superuser("super@test.fr", PWD)
        cls.admin = mk("admin@a.fr", PWD, role=Role.ADMIN, etablissement=cls.etab)
        cls.cadre = mk("cadre@a.fr", PWD, role=Role.CADRE, etablissement=cls.etab)
        cls.soignant = mk("soignant@a.fr", PWD, role=Role.SOIGNANT, etablissement=cls.etab, staff_id=17)
        cls.admin_b = mk("admin@b.fr", PWD, role=Role.ADMIN, etablissement=cls.autre)

    def setUp(self):
        cache.clear()  # remet à zéro la limitation de débit

    def login(self, email, password=PWD):
        return self.client.post("/api/v1/auth/login", {"email": email, "password": password}, format="json")

    def auth(self, user):
        tokens = self.login(user.email).json()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        return tokens

    def assertError(self, resp, status_code, code):
        self.assertEqual(resp.status_code, status_code, resp.content)
        body = resp.json()
        self.assertEqual(body["error"]["code"], code, body)
        self.assertIn("correlation_id", body["error"])
        self.assertIn("message", body["error"])


class LoginTests(Base):
    def test_login_renvoie_tokens_et_user(self):
        resp = self.login("CADRE@a.fr")  # email insensible à la casse
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        self.assertEqual(set(body), {"access", "refresh", "user"})
        self.assertEqual(body["user"]["role"], "CADRE")
        self.assertEqual(body["user"]["etablissement_id"], self.etab.pk)
        self.assertNotIn("password", body["user"])

    def test_claims_du_jeton_conformes_au_contrat(self):
        claims = decode(self.login("soignant@a.fr").json()["access"])
        self.assertEqual(claims["iss"], "hospiplan-identite")
        self.assertEqual(claims["aud"], "hospiplan-api")
        self.assertEqual(claims["type"], "access")
        self.assertEqual(str(claims["sub"]), str(self.soignant.pk))
        self.assertEqual(claims["etablissement_id"], self.etab.pk)
        self.assertEqual(claims["role"], "SOIGNANT")
        self.assertEqual(claims["staff_id"], 17)
        self.assertEqual(claims["email"], "soignant@a.fr")
        self.assertIn("jti", claims)
        self.assertLessEqual(claims["exp"] - claims["iat"], 15 * 60)

    def test_superadmin_sans_etablissement(self):
        claims = decode(self.login("super@test.fr").json()["access"])
        self.assertIsNone(claims["etablissement_id"])
        self.assertEqual(claims["role"], "SUPERADMIN")

    def test_mauvais_mot_de_passe_et_compte_inconnu_meme_reponse(self):
        a = self.login("cadre@a.fr", "faux")
        b = self.login("inconnu@a.fr", "faux")
        self.assertError(a, 401, "INVALID_CREDENTIALS")
        self.assertError(b, 401, "INVALID_CREDENTIALS")
        self.assertEqual(a.json()["error"]["message"], b.json()["error"]["message"])

    def test_etablissement_suspendu(self):
        Etablissement.objects.filter(pk=self.etab.pk).update(statut_abonnement="SUSPENDU")
        self.assertError(self.login("cadre@a.fr"), 403, "ETABLISSEMENT_SUSPENDU")

    def test_compte_desactive(self):
        Utilisateur.objects.filter(pk=self.cadre.pk).update(is_active=False)
        self.assertError(self.login("cadre@a.fr"), 401, "INVALID_CREDENTIALS")

    def test_limitation_des_tentatives(self):
        for _ in range(5):
            self.login("cadre@a.fr", "faux")
        self.assertError(self.login("cadre@a.fr", "faux"), 429, "RATE_LIMITED")


class TokenTests(Base):
    def test_me(self):
        self.auth(self.cadre)
        resp = self.client.get("/api/v1/auth/me")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["email"], "cadre@a.fr")

    def test_sans_jeton(self):
        self.assertError(self.client.get("/api/v1/auth/me"), 401, "AUTH_REQUIRED")

    def test_jeton_falsifie(self):
        access = self.login("cadre@a.fr").json()["access"]
        head, payload, sig = access.split(".")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {head}.{payload}.{sig[::-1]}")
        self.assertError(self.client.get("/api/v1/auth/me"), 401, "TOKEN_INVALID")

    def test_jeton_expire(self):
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        token = jwt.encode({"iss": "hospiplan-identite", "aud": "hospiplan-api", "sub": str(self.cadre.pk),
                            "type": "access", "role": "CADRE", "etablissement_id": self.etab.pk,
                            "iat": int(past.timestamp()), "exp": int((past + timedelta(minutes=15)).timestamp())},
                           settings.JWT_PRIVATE_KEY, algorithm="RS256")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertError(self.client.get("/api/v1/auth/me"), 401, "TOKEN_EXPIRED")

    def test_refresh_token_refuse_comme_access(self):
        refresh = self.login("cadre@a.fr").json()["refresh"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh}")
        self.assertError(self.client.get("/api/v1/auth/me"), 401, "TOKEN_INVALID")

    def test_refresh_rotation_et_revocation(self):
        refresh = self.login("cadre@a.fr").json()["refresh"]
        resp = self.client.post("/api/v1/auth/refresh", {"refresh": refresh}, format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertNotEqual(resp.json()["refresh"], refresh)
        # l'ancien refresh est révoqué
        again = self.client.post("/api/v1/auth/refresh", {"refresh": refresh}, format="json")
        self.assertError(again, 401, "TOKEN_INVALID")

    def test_refresh_relit_le_role_en_base(self):
        refresh = self.login("cadre@a.fr").json()["refresh"]
        Utilisateur.objects.filter(pk=self.cadre.pk).update(role=Role.ADMIN)
        access = self.client.post("/api/v1/auth/refresh", {"refresh": refresh}, format="json").json()["access"]
        self.assertEqual(decode(access)["role"], "ADMIN")

    def test_logout(self):
        tokens = self.auth(self.cadre)
        resp = self.client.post("/api/v1/auth/logout", {"refresh": tokens["refresh"]}, format="json")
        self.assertEqual(resp.status_code, 204)
        again = self.client.post("/api/v1/auth/refresh", {"refresh": tokens["refresh"]}, format="json")
        self.assertError(again, 401, "TOKEN_INVALID")

    def test_jwks_permet_de_verifier_un_jeton(self):
        jwk = self.client.get("/api/v1/auth/jwks").json()["keys"][0]
        self.assertEqual((jwk["kty"], jwk["alg"], jwk["use"]), ("RSA", "RS256", "sig"))
        key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(jwk))
        access = self.login("cadre@a.fr").json()["access"]
        jwt.decode(access, key, algorithms=["RS256"], audience="hospiplan-api")

    def test_correlation_id_propage(self):
        resp = self.client.get("/api/v1/auth/me", HTTP_X_CORRELATION_ID="test-corr-1234")
        self.assertEqual(resp["X-Correlation-ID"], "test-corr-1234")
        self.assertEqual(resp.json()["error"]["correlation_id"], "test-corr-1234")

    def test_health(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["service"], "service-identite")


class UtilisateurTests(Base):
    def test_admin_ne_voit_que_son_etablissement(self):
        self.auth(self.admin)
        emails = {u["email"] for u in self.client.get("/api/v1/users").json()["results"]}
        self.assertEqual(emails, {"admin@a.fr", "cadre@a.fr", "soignant@a.fr"})

    def test_admin_ne_peut_pas_lire_un_compte_d_un_autre_etablissement(self):
        self.auth(self.admin)
        self.assertError(self.client.get(f"/api/v1/users/{self.admin_b.pk}"), 404, "NOT_FOUND")

    def test_cadre_et_soignant_interdits(self):
        for user in (self.cadre, self.soignant):
            self.auth(user)
            self.assertError(self.client.get("/api/v1/users"), 403, "FORBIDDEN_ROLE")

    def test_admin_cree_dans_son_etablissement_meme_si_autre_demande(self):
        self.auth(self.admin)
        resp = self.client.post("/api/v1/users", {
            "email": "nouveau@a.fr", "first_name": "N", "last_name": "V", "role": "CADRE",
            "etablissement_id": self.autre.pk, "password": PWD}, format="json")
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.json()["etablissement_id"], self.etab.pk)
        self.assertEqual(self.login("nouveau@a.fr").status_code, 200)

    def test_admin_ne_peut_pas_creer_de_superadmin(self):
        self.auth(self.admin)
        resp = self.client.post("/api/v1/users", {"email": "x@a.fr", "role": "SUPERADMIN", "password": PWD},
                                format="json")
        self.assertError(resp, 400, "VALIDATION_ERROR")

    def test_email_en_double(self):
        self.auth(self.admin)
        resp = self.client.post("/api/v1/users", {"email": "CADRE@a.fr", "role": "CADRE", "password": PWD},
                                format="json")
        self.assertError(resp, 409, "CONFLICT")

    def test_soignant_sans_staff_id(self):
        self.auth(self.admin)
        resp = self.client.post("/api/v1/users", {"email": "s2@a.fr", "role": "SOIGNANT", "password": PWD},
                                format="json")
        self.assertError(resp, 400, "VALIDATION_ERROR")
        self.assertIn("staff_id", resp.json()["error"]["details"])

    def test_admin_cree_sans_preciser_l_etablissement(self):
        self.auth(self.admin)
        resp = self.client.post("/api/v1/users", {"email": "s3@a.fr", "role": "SOIGNANT", "staff_id": 18,
                                                  "password": PWD}, format="json")
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.json()["etablissement_id"], self.etab.pk)

    def test_staff_id_unique_par_etablissement(self):
        self.auth(self.admin)
        resp = self.client.post("/api/v1/users", {"email": "s4@a.fr", "role": "SOIGNANT", "staff_id": 17,
                                                  "password": PWD}, format="json")
        self.assertError(resp, 400, "VALIDATION_ERROR")

    def test_mot_de_passe_faible(self):
        self.auth(self.admin)
        resp = self.client.post("/api/v1/users", {"email": "w@a.fr", "role": "CADRE", "password": "123456"},
                                format="json")
        self.assertError(resp, 400, "VALIDATION_ERROR")

    def test_desactivation(self):
        self.auth(self.admin)
        self.assertEqual(self.client.delete(f"/api/v1/users/{self.cadre.pk}").status_code, 204)
        self.client.credentials()
        self.assertError(self.login("cadre@a.fr"), 401, "INVALID_CREDENTIALS")

    def test_pas_d_auto_desactivation(self):
        self.auth(self.admin)
        self.assertError(self.client.delete(f"/api/v1/users/{self.admin.pk}"), 400, "VALIDATION_ERROR")

    def test_superadmin_voit_tout_et_filtre(self):
        self.auth(self.superadmin)
        all_ = self.client.get("/api/v1/users").json()["count"]
        only_b = self.client.get(f"/api/v1/users?etablissement_id={self.autre.pk}").json()["results"]
        self.assertEqual(all_, 5)
        self.assertEqual([u["email"] for u in only_b], ["admin@b.fr"])


class EtablissementTests(Base):
    def test_superadmin_cree(self):
        self.auth(self.superadmin)
        resp = self.client.post("/api/v1/etablissements", {"nom": "CH C", "siret": "33333333333333",
                                                           "ville": "Lille", "plan": "PREMIUM"}, format="json")
        self.assertEqual(resp.status_code, 201, resp.content)

    def test_siret_invalide(self):
        self.auth(self.superadmin)
        resp = self.client.post("/api/v1/etablissements", {"nom": "X", "siret": "123", "ville": "Y"},
                                format="json")
        self.assertError(resp, 400, "VALIDATION_ERROR")

    def test_admin_lit_seulement_le_sien_et_ne_cree_pas(self):
        self.auth(self.admin)
        ids = [e["id"] for e in self.client.get("/api/v1/etablissements").json()["results"]]
        self.assertEqual(ids, [self.etab.pk])
        resp = self.client.post("/api/v1/etablissements", {"nom": "Z", "siret": "44444444444444", "ville": "Z"},
                                format="json")
        self.assertError(resp, 403, "FORBIDDEN_ROLE")

    def test_resiliation_bloque_la_connexion(self):
        self.auth(self.superadmin)
        self.assertEqual(self.client.delete(f"/api/v1/etablissements/{self.etab.pk}").status_code, 204)
        self.client.credentials()
        self.assertError(self.login("cadre@a.fr"), 403, "ETABLISSEMENT_SUSPENDU")


@override_settings(SERVICE_CLIENTS_JSON=CLIENTS)
class ServiceTokenTests(Base):
    def service_token(self, secret="s3cret-planning"):
        return self.client.post("/internal/v1/auth/service-token",
                                {"client_id": "service-planning", "client_secret": secret}, format="json")

    def test_emission(self):
        resp = self.service_token()
        self.assertEqual(resp.status_code, 200, resp.content)
        claims = decode(resp.json()["access"], audience="hospiplan-internal")
        self.assertEqual(claims["type"], "service")
        self.assertEqual(claims["sub"], "service-planning")
        self.assertEqual(claims["scope"], ["personnel:read"])
        self.assertEqual(resp.json()["expires_in"], 900)

    def test_mauvais_secret(self):
        self.assertError(self.service_token("faux"), 401, "INVALID_CREDENTIALS")

    def test_jeton_de_service_refuse_sur_api_publique(self):
        token = self.service_token().json()["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}", HTTP_X_ETABLISSEMENT_ID=str(self.etab.pk))
        self.assertError(self.client.get("/api/v1/users"), 403, "FORBIDDEN_ROLE")
