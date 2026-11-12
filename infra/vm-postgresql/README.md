# VM PostgreSQL (IaaS) — HospiPlan

Base de données des 3 microservices, hébergée sur une VM Azure (exigence IaaS du TP).

## Choix et justification (pour le livrable)

| Élément | Choix | Justification |
|---|---|---|
| OS | Ubuntu Server 24.04 LTS | support 5 ans, PostgreSQL 16 dans les dépôts officiels, gratuit |
| Taille | `Standard_B1s` (1 vCPU, 1 Gio) | burstable, charge de démo très faible ; passer en `B2s` si la génération de planning est lente |
| Disque | 30 Gio StandardSSD_LRS | données de démo < 1 Gio ; SSD standard = bon rapport prix/latence |
| Région | France Central | proximité des utilisateurs, données de santé en France |
| Ports ouverts | 22 (SSH) et 5432 (PostgreSQL) **uniquement depuis l'IP admin + IP sortantes des App Service** | tout le reste refusé (NSG `DenyAllInBound` + `ufw`) |
| Accès | SSH **par clé** uniquement, root interdit, fail2ban | pas de mot de passe exposé à la force brute |
| Sécurité BDD | SSL obligatoire à distance (`hostssl`), `scram-sha-256`, `public` révoqué, **un utilisateur et un schéma par microservice** | un service compromis ne lit pas les données des autres |
| Sauvegarde | `pg_dump` quotidien à 02:30, conservé 7 jours | restauration simple ; en production : Azure Backup / snapshot du disque |
| Coût | arrêt automatique à 19:00 UTC | VM facturée uniquement aux heures de travail |
| Pourquoi IaaS | contrôle total de la configuration PostgreSQL (schémas, `pg_hba`, extensions), coût inférieur au PaaS managé pour une démo | limite assumée : patchs, sauvegardes et haute disponibilité à notre charge → en production on passerait à *Azure Database for PostgreSQL Flexible Server* |

## Déploiement (responsable : B)

```bash
az login
az account set --subscription "<abonnement de la classe>"
cd infra/vm-postgresql
PREFIX=hospiplan SUFFIX=<initiales> ./deploy-vm.sh          # ~3 min

# attendre la fin de cloud-init puis créer bases/utilisateurs
ssh hospiadmin@<IP> 'cloud-init status --wait'
ssh hospiadmin@<IP> 'sudo bash -s' < setup-postgres.sh       # affiche les mots de passe UNE fois
```

Reporter les identifiants affichés :
- en local : dans `.env` (`DB_HOST=<IP>`, `DB_USER=hospiplan_app`, `DB_PASSWORD=...`, `DB_SSLMODE=require`) ;
- sur Azure : App Service → Configuration → Paramètres d'application (un utilisateur `svc_*` par service).

Après création des App Service :

```bash
az webapp show -g <RG> -n <app> --query outboundIpAddresses -o tsv
RG=<RG> APP_SERVICE_IPS="ip1 ip2 ..." ./update-nsg.sh
```

## Utilisateurs créés

| Utilisateur | Schéma | Usage |
|---|---|---|
| `hospiplan_app` | `public` | monolithe actuel (transition) — à supprimer après le découpage |
| `svc_identite` | `identite` | service-identite |
| `svc_personnel` | `personnel` | service-personnel |
| `svc_planning` | `planning` | service-planning |

## Tests post-déploiement

```bash
# depuis le poste admin : doit réussir
psql "host=<IP> dbname=hospiplan user=hospiplan_app sslmode=require" -c "select version();"
# sans SSL : doit être refusé
psql "host=<IP> dbname=hospiplan user=hospiplan_app sslmode=disable" -c "select 1;"
# depuis une autre IP : timeout (NSG)
```

## Suppression (fin du TP)

```bash
az group delete -n <RG> --yes --no-wait
```
