import streamlit as st
from formagroups import solve_grouping

# 1. Configuration de base de la page
st.set_page_config(page_title="FormaGroups", page_icon="👥")

st.title("FormaGroups Web")
st.markdown("""
Cet outil permet de répartir des auditeurs dans des ateliers en maximisant les nouvelles rencontres.
Veuillez charger votre fichier Excel. \n
Il doit impérativement contenir les 3 feuilles : 
**auditeurs**, **ateliers** et **exclusions**.
""")

st.markdown("### 1. Télécharger le modèle")
st.write("Si vous n'avez pas encore préparé vos données, téléchargez ce modèle d'exemple :")

# On ouvre le fichier présent dans le même dossier que app.py
try:
    with open("modèle_à_remplir.xlsx", "rb") as template_file:
        st.download_button(
            label="📝 Télécharger le modèle Excel",
            data=template_file, # Streamlit lit les données binaires du fichier
            file_name="modele_formagroups.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
except FileNotFoundError:
    # Message de secours si le fichier n'est pas trouvé dans le dossier
    st.warning("Le fichier modèle n'est pas disponible pour le moment.")


st.markdown("### 2. Lancer la répartition")
fichier_entree = st.file_uploader("Chargez votre fichier rempli (.xlsx)", type=["xlsx"])

# Optionnel mais recommandé : réinitialiser les résultats si l'utilisateur change de fichier
if fichier_entree is None and 'calcul_termine' in st.session_state:
    st.session_state.clear()

if fichier_entree is not None:
    
    # Le bouton sert UNIQUEMENT à lancer le calcul et remplir le coffre-fort
    if st.button("Lancer la répartition"):
        with st.spinner("Calcul des meilleurs groupes en cours..."):
            try:
                excel_buffer, texte_planning, stats_df = solve_grouping(fichier_entree, time_limit=5)
                
                # === NOUVEAUTÉ : On sauvegarde en mémoire (Session State) ===
                # Pour l'Excel, on stocke directement les octets avec getvalue()
                st.session_state['excel_bytes'] = excel_buffer.getvalue() 
                st.session_state['texte_planning'] = texte_planning
                st.session_state['stats_df'] = stats_df
                st.session_state['calcul_termine'] = True
                
            except Exception as e:
                st.error(f"Une erreur est survenue lors du calcul : {e}")

    # === NOUVEAUTÉ : On affiche les résultats stockés hors du bouton ===
    # Ainsi, ils résistent au rafraîchissement de la page !
    if st.session_state.get('calcul_termine', False):
        st.success("Répartition terminée avec succès !")
        
        st.subheader("📊 Statistiques de la répartition")
        st.dataframe(st.session_state['stats_df'], hide_index=True)
        
        st.subheader("📥 Récupérer les résultats")
        col1, col2 = st.columns(2)
        
        with col1:
            st.download_button(
                label="📄 Télécharger le planning (TXT)",
                data=st.session_state['texte_planning'],
                file_name="planning_ateliers.txt",
                mime="text/plain"
            )
            
        with col2:
            st.download_button(
                label="📊 Télécharger les groupes et les détails (Excel)",
                data=st.session_state['excel_bytes'],
                file_name="output_groupes.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )