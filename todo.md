# TODO — IA Gomoku (projet 42)

Roadmap pédagogique pour ajouter une IA au projet. Chaque phase =
d'abord ce qu'il faut **comprendre**, puis ce qu'il faut **coder**.
Fais les phases dans l'ordre : chacune s'appuie sur la précédente.

Contraintes du sujet 42 à garder en tête tout du long :
- **≤ 500 ms** par coup joué par l'IA.
- Doit afficher le **temps de réflexion** de chaque coup.
- Modes **Humain vs IA** et **IA vs IA**.
- **Suggestion de coup** pour un joueur humain.
- L'IA doit respecter *toutes* les règles (captures, double-trois, win
  par capture, alignement en attente).

---

## Phase 0 — Préparer le terrain (½ journée)

### À comprendre
- La séparation actuelle : `board.py` = état pur, `rules.py` = légalité,
  `game.py` = orchestration. L'IA doit **lire** `Board` + `rules` mais
  ne doit jamais muter `Game` — elle propose un coup, `Game.play(r, c)`
  le joue.
- Notion de **copie profonde** de l'état : l'IA va simuler des milliers
  de coups, elle ne doit pas polluer le vrai plateau.

### À coder
- [ ] Créer `ai.py` avec une fonction stub `choose_move(game) -> (r, c)`
      qui renvoie pour l'instant un coup aléatoire légal.
- [ ] Créer une classe `Player` (ou juste deux fonctions) : `HumanPlayer`
      (attend un clic UI) et `AIPlayer` (appelle `choose_move`).
- [ ] Dans `game.py`, ne rien changer côté logique — juste exposer ce
      qu'il faut pour que l'IA puisse lire l'état sans y toucher :
      `board`, `current`, `captures`, `pending_alignment_*`.
- [ ] Écran de démarrage UI : choix Humain/IA pour chaque couleur.
- [ ] Vérifier qu'une partie IA-aléatoire vs IA-aléatoire va au bout
      sans crash. C'est ta baseline.

**Piège classique** : ne pas oublier que les captures modifient le
plateau. Si tu simules un coup, tu dois aussi simuler les captures.
Réutilise `board.find_captures()` — ne réimplémente pas.

---

## Phase 1 — Minimax nu (1 journée)

### À comprendre / à lire
- **Algorithme minimax** : arbre de recherche à profondeur fixe, deux
  joueurs, MAX (moi) veut maximiser, MIN (adversaire) veut minimiser
  une fonction d'évaluation.
- **Fonction d'évaluation** : donne un score à une position *sans*
  chercher plus loin. Score positif = bon pour moi, négatif = bon pour
  l'adversaire. `+∞` = j'ai gagné, `-∞` = j'ai perdu.
- Lire au moins l'article Wikipédia FR "Algorithme minimax" et regarder
  un pseudo-code (Russell & Norvig chap. 5 si tu l'as sous la main).

### À coder
- [ ] `evaluate(board, color) -> int` : version naïve. Compte les
      alignements de 2, 3, 4 stones pour `color` (positif) et pour
      l'adversaire (négatif). Pondération grossière au début (ex : 10,
      100, 1000, 100000 pour 5). Prends aussi en compte les captures :
      chaque paire capturée compte gros (~50 par pierre).
- [ ] `minimax(state, depth, maximizing_color) -> (score, move)`. À
      profondeur 0 ou état terminal, renvoie `evaluate(...)`. Sinon
      itère sur les coups légaux, recurse, prend le max ou le min.
- [ ] Brancher `choose_move()` sur minimax profondeur 2.
- [ ] Chronométrer une profondeur 2 sur plateau vide : ça va être
      **lent** (19×19 = 361 coups, 361² = 130 000 positions rien qu'à
      la profondeur 2). C'est normal, c'est la phase suivante qui règle
      ça.

**Piège** : minimax naïf sur du 19×19 est inutilisable au-delà de la
profondeur 2. Ne t'acharne pas à optimiser cette version — passe
directement à la Phase 2.

---

## Phase 2 — Alpha-Beta pruning (1 journée)

### À comprendre
- **Élagage alpha-beta** : deux bornes `α` (meilleure garantie de MAX)
  et `β` (meilleure garantie de MIN). Si à un nœud MIN on trouve un
  score ≤ α, on coupe : MAX ne jouera jamais ici. Symétrique pour MAX.
- Complexité passe de O(b^d) à O(b^(d/2)) **si l'ordre des coups est
  bon**. Autrement dit, l'ordering est aussi important que l'élagage.
- Concept de **negamax** : simplification quand la fonction d'éval est
  antisymétrique (`eval(pos, me) = -eval(pos, opp)`). Un seul chemin de
  code au lieu de deux (MAX/MIN).

### À coder
- [ ] Réécrire `minimax` en **negamax avec alpha-beta**. Signature
      typique : `negamax(state, depth, alpha, beta, color) -> (score, move)`.
- [ ] Adapter `evaluate` pour qu'elle renvoie un score du **point de
      vue du joueur courant** (négatif si sa position est mauvaise).
- [ ] Tester : à profondeur 3 tu dois passer sous les ~2 secondes sur
      un plateau mi-partie. Si non, ton ordering est mauvais ou ton
      eval est trop lourde.

---

## Phase 3 — Réduire l'espace de recherche (1 journée)

### À comprendre
- **Génération de coups candidats** : jouer au centre d'un plateau vide
  est absurde à évaluer sur 361 cases. Un coup n'a de sens que **près
  d'une pierre existante** (typiquement voisinage à distance ≤ 2).
- Cela fait tomber le facteur de branchement de ~360 à ~20-40 en
  milieu de partie. Gain énorme.

### À coder
- [ ] `generate_candidates(board) -> list[(r, c)]` : renvoie les cases
      vides à distance de Chebyshev ≤ 2 d'au moins une pierre. Cas
      spécial : plateau vide → renvoyer juste `(9, 9)` (le centre).
- [ ] Utiliser cette liste dans negamax au lieu de toutes les cases.
- [ ] **Filtrer les coups illégaux** (double-trois) *avant* la recurse,
      pas dans l'évaluation.
- [ ] Nouveau bench : profondeur 4 doit rentrer sous la seconde en
      milieu de partie.

---

## Phase 4 — Move ordering (½ journée)

### À comprendre
- L'alpha-beta ne coupe efficacement que si on essaie les **meilleurs
  coups en premier**. Si tu explores le pire coup d'abord, tu ne coupes
  rien.
- Heuristiques classiques :
  1. Coups qui gagnent (aligne 5).
  2. Coups qui bloquent une victoire adverse.
  3. Coups qui capturent.
  4. Coups qui créent un free-four ou double-three menaçant.
  5. Coups proches du dernier coup joué.

### À coder
- [ ] `score_candidate(board, r, c, color) -> int` : score rapide sans
      recurse. Utilisé uniquement pour trier.
- [ ] Trier `generate_candidates()` par ce score, en ordre décroissant,
      avant de les passer à negamax.
- [ ] Tu devrais gagner un facteur 2 à 5 en vitesse à profondeur égale.

---

## Phase 5 — Iterative Deepening + budget temps (½ journée)

### À comprendre
- **Iterative deepening** : au lieu de dire "je cherche à profondeur
  N", tu cherches à profondeur 1, puis 2, puis 3… en gardant à chaque
  itération le meilleur coup trouvé. Quand le temps est écoulé, tu
  renvoies le meilleur coup de la dernière itération **complète**.
- Contre-intuitif mais vrai : ça ne coûte quasi rien (chaque niveau est
  ~b fois plus gros que le précédent, donc le coût total est dominé par
  le dernier niveau). Et ça donne une garantie de réponse.
- Bonus : le meilleur coup de la profondeur N-1 sert de premier coup à
  essayer à la profondeur N → ordering amélioré gratuitement.

### À coder
- [ ] Wrapper `choose_move()` : boucle `for depth in range(1, MAX_D):`
      qui appelle negamax avec un check `time.perf_counter()`.
- [ ] Passer un `deadline` à travers les appels récursifs. Si dépassé,
      lever une exception (`TimeoutError`) et attraper au top-level.
- [ ] Budget cible : **450 ms** (marge de 50 ms sur les 500 ms du
      sujet, pour ne pas dépasser à cause d'un dernier niveau qui
      déborde).
- [ ] Afficher le temps réel dans l'UI (déjà branché pour l'humain,
      étends-le à l'IA).

**Piège** : ne pas renvoyer le coup partiel d'une itération
interrompue — il est basé sur une exploration incomplète et peut être
franchement mauvais. Toujours renvoyer le coup de la **dernière
profondeur terminée**.

---

## Phase 6 — Heuristique sérieuse (1 à 2 journées)

### À comprendre
- **Patterns Gomoku** classiques (à reconnaître dans l'éval) :
  - `.XXXX.` = **open four** — victoire au prochain coup, imparable
    sans capture.
  - `.XXXX` ou `XXXX.` (fermé un côté) = **four** — force l'adversaire
    à bloquer.
  - `.XXX.` = **open three** (free-three) — menace de devenir open
    four.
  - `.XX.X.`, `.X.XX.` = free-threes "cassés".
  - `.XX.` = open two.
- **Double-menace** : deux fours simultanés, ou un four + un
  free-three, sont gagnants.
- Prise en compte des **captures** dans l'éval : chaque pierre à 1 de
  10 devient très précieuse. À 9/10, une seule capture supplémentaire
  = victoire.
- **Alignement en attente** (`pending_alignment`) : si tu es sous
  menace, l'éval doit refléter l'urgence de casser l'alignement (par
  capture).

### À coder
- [ ] Refonte de `evaluate()` : parcourt le plateau axis par axis,
      pattern-matche les motifs ci-dessus, somme les scores pondérés.
      Pondérations indicatives (à ajuster) :
      - Open four : 100 000
      - Four fermé : 10 000
      - Open three : 5 000
      - Broken three : 2 000
      - Open two : 200
      - Chaque pierre capturée : 500
      - Bonus exponentiel proche de 10 captures.
- [ ] Bonus double-menace : détecter si deux threats sont créées par le
      même coup → +50 000.
- [ ] Prendre en compte l'état `pending_alignment` dans l'éval si tu le
      passes au `state`.

**Test manuel obligatoire** : joue contre ton IA. Si elle laisse un
free-three sans le bloquer, ta pondération "menace adverse" est trop
faible. Si elle joue défensif alors qu'elle peut gagner, l'inverse.


## Phase 7 — Suggestion de coup + IA vs IA (½ journée)

- [ ] **Hint mode** : bouton "Hint" dans l'UI. Appelle `choose_move()`
      pour le joueur humain courant, affiche le coup en surbrillance
      (pas de vert clignotant, discret — juste un contour). Contrainte
      : ne pas jouer, juste suggérer.
- [ ] **IA vs IA** : boucle qui alterne `choose_move()` puis
      `game.play()`, laisse un `plt.pause(0.05)` entre les deux pour
      que la UI se rafraîchisse.
- [ ] **Affichage du temps IA** : réutilise `move_times` — c'est déjà
      symétrique par couleur.

---

## Phase 8 — Validation finale

- [ ] IA vs IA aléatoire : ton IA doit gagner ~100% des parties.
- [ ] IA vs joueur amateur : ton IA doit gagner la majorité.
- [ ] Aucune partie ne doit dépasser 500 ms sur un coup. Log les
      dépassements.
- [ ] L'IA ne doit **jamais** tenter un coup illégal (double-trois).
      `is_legal()` doit être appelé en dernier avant renvoi.
- [ ] Tester les cas limites : alignement en attente à défendre,
      capture obligatoire pour survivre, position 9/10 captures.

