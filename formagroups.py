import math
import pandas as pd
from itertools import combinations
from ortools.sat.python import cp_model
import io


def export_planning_txt(groups_df, ateliers_df):
    """
    Exporte un fichier texte au format :
    Atelier / Intitulé / Taille des groupes / Groupes / Membres
    """
    if "intitule" not in ateliers_df.columns:
        ateliers_df["intitule"] = ""
    if "capacite" not in ateliers_df.columns:
        raise ValueError("La feuille 'ateliers' doit contenir la colonne 'capacite'.")

    title_map = dict(zip(ateliers_df["atelier_id"], ateliers_df["intitule"]))
    cap_map = dict(zip(ateliers_df["atelier_id"], ateliers_df["capacite"]))

    lines = []
    lines.append("PLANNING DES ATELIERS")
    lines.append("=" * 80)
    lines.append("")

    ordered_workshops = ateliers_df["atelier_id"].tolist()

    for w in ordered_workshops:
        subset_w = groups_df[groups_df["atelier_id"] == w]
        if subset_w.empty:
            continue

        lines.append(f"Atelier: {w}")
        lines.append(f"Intitulé: {title_map.get(w, '')}")
        lines.append(f"Taille des groupes : {cap_map.get(w, '')}")
        lines.append("-" * 80)

        for g in sorted(subset_w["groupe"].unique()):
            subset_g = subset_w[subset_w["groupe"] == g].sort_values("ordre_dans_groupe")
            lines.append(f"  {g}")
            for _, r in subset_g.iterrows():
                lines.append(f"    - {r['auditeur_nom']} ({r['auditeur_id']})")
            lines.append("")

        lines.append("")

    texte_complet = "\n".join(lines)
    return texte_complet


def solve_grouping(input_file="input.xlsx", time_limit=60):
    # =========================
    # 1) Lecture Excel
    # =========================
    auditeurs_df = pd.read_excel(input_file, sheet_name="auditeurs")
    ateliers_df = pd.read_excel(input_file, sheet_name="ateliers")
    exclusions_df = pd.read_excel(input_file, sheet_name="exclusions")

    # Colonnes attendues
    if not {"id", "nom"}.issubset(auditeurs_df.columns):
        raise ValueError("Feuille 'auditeurs' doit contenir: id, nom")
    if not {"atelier_id", "capacite"}.issubset(ateliers_df.columns):
        raise ValueError("Feuille 'ateliers' doit contenir: atelier_id, capacite")
    if not {"id1", "id2"}.issubset(exclusions_df.columns):
        raise ValueError("Feuille 'exclusions' doit contenir: id1, id2")

    # Intitulé optionnel (on le crée si absent)
    if "intitule" not in ateliers_df.columns:
        ateliers_df["intitule"] = ""

    # Nettoyage
    auditeurs_df["id"] = auditeurs_df["id"].astype(str).str.strip()
    auditeurs_df["nom"] = auditeurs_df["nom"].astype(str).str.strip()

    ateliers_df["atelier_id"] = ateliers_df["atelier_id"].astype(str).str.strip()
    ateliers_df["intitule"] = ateliers_df["intitule"].fillna("").astype(str).str.strip()
    ateliers_df["capacite"] = ateliers_df["capacite"].astype(int)

    exclusions_df["id1"] = exclusions_df["id1"].astype(str).str.strip()
    exclusions_df["id2"] = exclusions_df["id2"].astype(str).str.strip()

    auditors = auditeurs_df["id"].tolist()
    auditor_name = dict(zip(auditeurs_df["id"], auditeurs_df["nom"]))

    workshops = ateliers_df["atelier_id"].tolist()
    capacity = dict(zip(ateliers_df["atelier_id"], ateliers_df["capacite"]))

    n = len(auditors)
    if n == 0:
        raise ValueError("Aucun auditeur trouvé dans la feuille 'auditeurs'.")

    # Nombre de groupes par atelier (selon capacité)
    groups_per_workshop = {w: math.ceil(n / capacity[w]) for w in workshops}

    # Vérif capacité globale
    for w in workshops:
        total_places = groups_per_workshop[w] * capacity[w]
        if total_places < n:
            raise ValueError(f"Atelier {w}: capacité insuffisante pour placer tout le monde.")

    # Exclusions normalisées
    exclusions = set()
    auditor_set = set(auditors)
    for _, r in exclusions_df.iterrows():
        i, j = r["id1"], r["id2"]
        if i in auditor_set and j in auditor_set and i != j:
            a, b = sorted([i, j])
            exclusions.add((a, b))

    pairs = list(combinations(auditors, 2))

    # =========================
    # 2) Modèle CP-SAT
    # =========================
    model = cp_model.CpModel()

    # x[a,w,g] = auditeur a dans groupe g de l'atelier w
    x = {}
    for a in auditors:
        for w in workshops:
            for g in range(groups_per_workshop[w]):
                x[(a, w, g)] = model.NewBoolVar(f"x_{a}_{w}_g{g}")

    # Chaque auditeur exactement dans 1 groupe de chaque atelier
    for a in auditors:
        for w in workshops:
            model.Add(sum(x[(a, w, g)] for g in range(groups_per_workshop[w])) == 1)

    # Taille max groupe
    for w in workshops:
        for g in range(groups_per_workshop[w]):
            model.Add(sum(x[(a, w, g)] for a in auditors) <= capacity[w])

    # y[i,j,w,g] = i et j ensemble dans groupe g de l'atelier w
    y = {}
    for i, j in pairs:
        for w in workshops:
            for g in range(groups_per_workshop[w]):
                y[(i, j, w, g)] = model.NewBoolVar(f"y_{i}_{j}_{w}_g{g}")
                model.Add(y[(i, j, w, g)] <= x[(i, w, g)])
                model.Add(y[(i, j, w, g)] <= x[(j, w, g)])
                model.Add(y[(i, j, w, g)] >= x[(i, w, g)] + x[(j, w, g)] - 1)

    # meet_count[i,j] = nb de rencontres entre i et j
    meet_count = {}
    for i, j in pairs:
        meet_count[(i, j)] = model.NewIntVar(0, len(workshops), f"meet_{i}_{j}")
        model.Add(
            meet_count[(i, j)] ==
            sum(y[(i, j, w, g)] for w in workshops for g in range(groups_per_workshop[w]))
        )

    # met_once[i,j] = 1 si au moins une rencontre
    met_once = {}
    for i, j in pairs:
        met_once[(i, j)] = model.NewBoolVar(f"met_once_{i}_{j}")
        model.Add(meet_count[(i, j)] >= 1).OnlyEnforceIf(met_once[(i, j)])
        model.Add(meet_count[(i, j)] == 0).OnlyEnforceIf(met_once[(i, j)].Not())

    # Exclusions
    for i, j in exclusions:
        for w in workshops:
            for g in range(groups_per_workshop[w]):
                model.Add(x[(i, w, g)] + x[(j, w, g)] <= 1)

    # Objectif: max couverture des rencontres + bonus sur volume total
    obj_cover = sum(met_once[(i, j)] for i, j in pairs)
    obj_total = sum(meet_count[(i, j)] for i, j in pairs)
    model.Maximize(1000 * obj_cover + obj_total)

    # =========================
    # 3) Solve
    # =========================
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_search_workers = 8

    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError("Aucune solution faisable trouvée.")

    # =========================
    # 4) Préparation des sorties
    # =========================
    # A) Groupes par atelier
    rows_groups = []
    for w in workshops:
        for g in range(groups_per_workshop[w]):
            members = [a for a in auditors if solver.Value(x[(a, w, g)]) == 1]
            if not members:
                continue
            members_sorted = sorted(members, key=lambda z: auditor_name[z].lower())
            for rank, a in enumerate(members_sorted, start=1):
                rows_groups.append({
                    "atelier_id": w,
                    "intitule": ateliers_df.loc[ateliers_df["atelier_id"] == w, "intitule"].iloc[0],
                    "groupe": f"G{g+1}",
                    "ordre_dans_groupe": rank,
                    "auditeur_id": a,
                    "auditeur_nom": auditor_name[a]
                })

    groups_df = pd.DataFrame(rows_groups).sort_values(
        ["atelier_id", "groupe", "ordre_dans_groupe"]
    )

    # B) Matrice de rencontres
    meet_matrix = pd.DataFrame(0, index=auditors, columns=auditors, dtype=int)
    for i, j in pairs:
        c = solver.Value(meet_count[(i, j)])
        meet_matrix.loc[i, j] = c
        meet_matrix.loc[j, i] = c

    label = {a: f"{a} - {auditor_name[a]}" for a in auditors}
    meet_matrix_named = meet_matrix.copy()
    meet_matrix_named.index = [label[a] for a in meet_matrix.index]
    meet_matrix_named.columns = [label[a] for a in meet_matrix.columns]

    # C) Liens pair à pair
    rows_links = []
    for i, j in pairs:
        rows_links.append({
            "auditeur1_id": i,
            "auditeur1_nom": auditor_name[i],
            "auditeur2_id": j,
            "auditeur2_nom": auditor_name[j],
            "nb_rencontres": solver.Value(meet_count[(i, j)]),
            "rencontre_au_moins_une_fois": solver.Value(met_once[(i, j)])
        })

    links_df = pd.DataFrame(rows_links).sort_values(
        ["nb_rencontres", "auditeur1_nom", "auditeur2_nom"],
        ascending=[False, True, True]
    )

    # D) Stats
    total_pairs = len(pairs)
    covered_pairs = int(sum(solver.Value(met_once[(i, j)]) for i, j in pairs))
    coverage_pct = 100 * covered_pairs / total_pairs if total_pairs else 0

    stats_df = pd.DataFrame([{
        "nb_auditeurs": len(auditors),
        "nb_ateliers": len(workshops),
        "nb_paires_total": total_pairs,
        "nb_paires_rencontrees_au_moins_1_fois": covered_pairs
    }])

    # =========================
    # 5) Exports
    # =========================
    excel_buffer = io.BytesIO()
    
    with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
        groups_df.to_excel(writer, sheet_name="groupes_par_atelier", index=False)
        meet_matrix_named.to_excel(writer, sheet_name="matrice_rencontres")
        links_df.to_excel(writer, sheet_name="liens_pair_a_pair", index=False)
        stats_df.to_excel(writer, sheet_name="stats", index=False)
    
    # Très important : on remet le curseur au début du fichier virtuel
    # Sinon, lors du téléchargement, le fichier semblera vide !
    excel_buffer.seek(0) 

    # 2. On récupère le texte du planning grâce à notre fonction modifiée
    texte_planning = export_planning_txt(groups_df, ateliers_df)

    # 3. On retourne l'Excel virtuel, le texte, et pourquoi pas les stats 
    # pour les afficher directement sur la page web !
    return excel_buffer, texte_planning, stats_df

