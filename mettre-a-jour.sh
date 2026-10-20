#!/bin/bash
# Met à jour le calendrier et le publie sur GitHub si un match a changé.
# Lancé toutes les 3 h par GitHub Actions et par le Mac : la LNB bloque les
# serveurs de GitHub, c'est donc le Mac qui rafraîchit les matchs LNB.
set -uo pipefail
cd "$(dirname "$0")"
ORIGINE="${ORIGINE:-Mac}"

for essai in 1 2 3; do
  # Le dépôt local ne contient que des fichiers générés : on repart toujours de GitHub
  git fetch -q origin main && git reset -q --hard origin/main || exit 1
  python3 build_calendar.py || exit 1
  git add sluc-nancy.ics cache.json
  # DTSTAMP change à chaque exécution : on ne publie que si un match a changé
  if git diff --cached -U0 | grep -E '^[+-][A-Z]' | grep -vE '^[+-]DTSTAMP' | grep -q .; then
    git commit -q -m "Mise à jour des matchs $(date -u +%F) ($ORIGINE)"
  elif [ $(( $(date +%s) - $(git log -1 --format=%ct) )) -gt 2160000 ]; then
    # GitHub coupe les tâches planifiées après 60 jours sans activité (intersaison)
    git commit -q --allow-empty -m "Vérification $(date -u +%F) : aucun changement ($ORIGINE)"
  else
    echo "Aucun changement"
    exit 0
  fi
  git push -q origin HEAD:main && echo "Publié" && exit 0
  echo "Publication refusée (mise à jour simultanée), nouvel essai…"
done
exit 1
