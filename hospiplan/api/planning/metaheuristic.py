"""
Métaheuristique - Recherche Tabou (Tabu Search) - Phase 3.

Pourquoi tabou plutôt que recuit simulé ?
    Sur les problèmes de staffing, la recherche tabou est généralement plus
    performante que le recuit simulé car :
      - elle gère bien les voisinages structurés (swap / reassignment),
      - la liste tabou évite les cycles courts fréquents en staffing
        (échanges A↔B qu'on annule puis qu'on refait),
      - les critères d'aspiration permettent de conserver une amélioration
        globale même si elle passe par un mouvement tabou.

Principe :
    Partant du planning glouton (toutes dures respectées), on itère en
    choisissant à chaque pas le MEILLEUR voisin non tabou, même s'il dégrade
    le score. On sauvegarde la meilleure solution rencontrée. On s'arrête
    après `max_iter` itérations sans amélioration ou `time_limit_s` secondes.

Voisinage (tous les mouvements préservent les dures — sinon rejetés) :
    - REASSIGN : retirer un soignant d'un shift, le remplacer par un autre légal.
    - SWAP    : échanger les soignants de deux shifts (si les deux mouvements restent légaux).
"""

import copy
import random
import time
from collections import deque

from . import scoring


def _snapshot(ctx):
    """Copie légère des affectations (suffisant pour restaurer un état)."""
    return {
        sid: list(lst) for sid, lst in ctx.assignments_by_staff.items()
    }


def _restore(ctx, snap):
    ctx.assignments_by_staff.clear()
    for sid, lst in snap.items():
        ctx.assignments_by_staff[sid] = list(lst)


def _assignments_in_window(ctx):
    """Liste [(staff_id, shift_id)] limitée aux shifts de la fenêtre."""
    out = []
    for staff_id, lst in ctx.assignments_by_staff.items():
        for (_, _, shift_id, _) in lst:
            if shift_id in ctx.shifts:
                out.append((staff_id, shift_id))
    return out


def tabu_search(ctx, aux, weights, max_iter=200, tabu_len=25, time_limit_s=8.0, seed=None):
    """
    Améliore le planning `ctx` sans violer les contraintes dures.

    Args:
        ctx, aux, weights : sortie de generator.generate_daily_planning().
        max_iter      : itérations max.
        tabu_len      : taille de la liste tabou FIFO.
        time_limit_s  : budget temps (secondes).
        seed          : reproductibilité.

    Returns:
        dict { 'best_score': ..., 'best_snapshot': ..., 'iterations': n }
        (le snapshot est restauré dans ctx avant retour).
    """
    if seed is not None:
        random.seed(seed)

    current_score = scoring.total_score(ctx, aux, weights)['total']
    best_score = current_score
    best_snapshot = _snapshot(ctx)

    tabu = deque(maxlen=tabu_len)  # éléments : tuples (shift_id, old_staff, new_staff)
    no_improve = 0
    start = time.time()
    iterations = 0

    all_staff_ids = aux['all_staff_ids']

    while iterations < max_iter and no_improve < 50:
        if time.time() - start > time_limit_s:
            break
        iterations += 1

        best_move = None
        best_move_score = None
        best_move_signature = None

        assignments = _assignments_in_window(ctx)
        if not assignments:
            break

        # On échantillonne un sous-ensemble de mouvements pour rester rapide
        sample_size = min(len(assignments), 30)
        sampled = random.sample(assignments, sample_size)

        for (staff_id, shift_id) in sampled:
            # ── Mouvement REASSIGN : remplacer staff_id par un autre légal ──
            ctx.remove_assignment(staff_id, shift_id)
            for candidate in all_staff_ids:
                if candidate == staff_id:
                    continue
                # déjà sur ce shift ?
                if any(sid == shift_id for (_, _, sid, _) in ctx.assignments_by_staff[candidate]):
                    continue
                ok, _ = ctx.is_assignment_legal(candidate, shift_id)
                if not ok:
                    continue

                ctx.add_assignment(candidate, shift_id)
                new_score = scoring.total_score(ctx, aux, weights)['total']
                signature = ('reassign', shift_id, staff_id, candidate)
                reverse_sig = ('reassign', shift_id, candidate, staff_id)

                is_tabu = reverse_sig in tabu
                aspires = new_score < best_score  # critère d'aspiration
                accept_candidate = (not is_tabu) or aspires

                if accept_candidate and (best_move_score is None or new_score < best_move_score):
                    best_move_score = new_score
                    best_move = ('reassign', shift_id, staff_id, candidate)
                    best_move_signature = signature

                ctx.remove_assignment(candidate, shift_id)
            # restaure l'affectation d'origine
            ctx.add_assignment(staff_id, shift_id)

        if best_move is None:
            break  # plus aucun voisin valide

        # Applique le meilleur mouvement
        _, shift_id, old_staff, new_staff = best_move
        ctx.remove_assignment(old_staff, shift_id)
        ctx.add_assignment(new_staff, shift_id)
        tabu.append(best_move_signature)
        current_score = best_move_score

        if current_score < best_score:
            best_score = current_score
            best_snapshot = _snapshot(ctx)
            no_improve = 0
        else:
            no_improve += 1

    # Restaure la meilleure solution trouvée
    _restore(ctx, best_snapshot)

    return {
        'best_score': best_score,
        'iterations': iterations,
        'elapsed_s': round(time.time() - start, 3),
    }
