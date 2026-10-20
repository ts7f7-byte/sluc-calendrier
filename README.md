# Calendrier SLUC Nancy Basket

Tous les matchs du SLUC Nancy Basket (Betclic Élite, playoffs, FIBA Europe Cup), mis à jour automatiquement toutes les 3 heures.

**S'abonner sur iPhone** : ouvrir ce lien dans Safari puis toucher « S'abonner »

webcal://raw.githubusercontent.com/ts7f7-byte/sluc-calendrier/main/sluc-nancy.ics

## Fonctionnement
- `build_calendar.py` lit les calendriers officiels LNB et FIBA et génère `sluc-nancy.ics`.
- `mettre-a-jour.sh` publie le fichier s'il a changé. Il est lancé par GitHub Actions et par le Mac
  (tâche `com.sluc-calendrier.update`) : la LNB bloque les serveurs de GitHub, c'est donc le Mac qui rafraîchit les matchs LNB.
