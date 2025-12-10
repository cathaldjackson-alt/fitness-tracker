import streamlit as st # Make sure streamlit is imported before using st.secrets
import pandas as pd
from datetime import datetime
import altair as alt
import json
import firebase_admin
from firebase_admin import credentials, firestore

# --- FIREBASE SETUP (UPDATED FOR CLOUD & LOCAL) ---
if not firebase_admin._apps:
    # 1. Try loading from Streamlit Secrets (Cloud Method)
    if 'firebase_key' in st.secrets:
        # We parse the secret JSON string back into a dictionary
        key_dict = json.loads(st.secrets['firebase_key'])
        cred = credentials.Certificate(key_dict)
        firebase_admin.initialize_app(cred)
    
    # 2. If no secrets, try loading from local file (PC Method)
    else:
        try:
            cred = credentials.Certificate('firebase_key.json')
            firebase_admin.initialize_app(cred)
        except:
            st.error("⚠️ Firebase key not found! Check secrets or local key file.")
            st.stop()

# Connect to DB
try:
    db = firestore.client()
except:
    st.error("⚠️ Database connection failed.")
    st.stop()

st.set_page_config(page_title="Cloud FitTrack", page_icon="☁️", layout="wide")
# --- DATABASE FUNCTIONS (REWRITTEN FOR FIREBASE) ---

def add_workout(date, category, sub_type, duration, distance, pace, structure, rpe, notes):
    # In Firestore, we create a dictionary and push it
    data = {
        "date": date.strftime("%Y-%m-%d"), # Store date as string for simplicity
        "category": category,
        "sub_type": sub_type,
        "duration_min": duration,
        "distance_km": distance,
        "pace": pace,
        "structure": structure,
        "rpe": rpe,
        "notes": notes,
        "created_at": firestore.SERVER_TIMESTAMP # Good for sorting
    }
    db.collection("workouts").add(data)

def delete_workout(workout_id):
    # Firestore deletes by Document ID
    db.collection("workouts").document(workout_id).delete()

def load_data():
    # Stream all documents from 'workouts' collection
    docs = db.collection("workouts").stream()
    
    data = []
    for doc in docs:
        d = doc.to_dict()
        d['id'] = doc.id # Capture the Firestore ID so we can delete it later
        data.append(d)
        
    df = pd.DataFrame(data)
    if not df.empty:
        df['date'] = pd.to_datetime(df['date'])
    return df

# --- CALLBACK FUNCTION ---
def save_workout_callback():
    if not st.session_state.confirm_save:
        st.session_state['warning_msg'] = "⚠️ Please check 'Ready to Save' to confirm."
        return

    # Gather Data
    date = st.session_state.date
    category = st.session_state.category
    duration = st.session_state.duration
    notes = st.session_state.notes
    rpe = st.session_state.rpe
    
    sub_type = "Normal"
    structure = "" 
    
    if category == "Running":
        sub_type = st.session_state.subtype_run
        if sub_type == "Workout":
            structure = st.session_state.structure_input
    elif category == "Cycling":
        sub_type = st.session_state.subtype_ride
        if sub_type == "Workout":
            structure = st.session_state.structure_input

    # Distance & Pace
    distance = 0.0
    pace_str = "N/A"

    if category == "Running":
        distance = st.session_state.distance
        if st.session_state.manual_pace:
            pace_str = st.session_state.pace_input
        else:
            if distance > 0:
                pace_decimal = duration / distance
                minutes = int(pace_decimal)
                seconds = int((pace_decimal - minutes) * 60)
                pace_str = f"{minutes}:{seconds:02d} /km"
    elif category == "Cycling":
        distance = st.session_state.distance_cycle
        if distance > 0 and duration > 0:
            speed = distance / (duration / 60)
            pace_str = f"{speed:.1f} km/h"
    elif category == "Swimming":
        distance = st.session_state.distance_swim

    # Save to Firebase
    add_workout(date, category, sub_type, duration, distance, pace_str, structure, rpe, notes)
    
    st.session_state['success_msg'] = f"✅ Saved {sub_type} ({category}) to Cloud!"
    st.session_state['warning_msg'] = None

    # Reset inputs
    st.session_state.duration = 30
    st.session_state.notes = ""
    st.session_state.confirm_save = False
    st.session_state.manual_pace = False
    st.session_state.pace_input = ""
    st.session_state.rpe = 5
    if 'structure_input' in st.session_state: st.session_state.structure_input = ""
    if 'distance' in st.session_state: st.session_state.distance = 0.0
    if 'distance_cycle' in st.session_state: st.session_state.distance_cycle = 0.0
    if 'distance_swim' in st.session_state: st.session_state.distance_swim = 0.0

# --- APP UI START ---
st.sidebar.header("Navigation")
page = st.sidebar.radio("Go to", ["Dashboard", "Log Workout", "History / Edit"])

if page == "Log Workout":
    st.title("📝 Log Activity (Cloud)")
    
    if st.session_state.get('success_msg'):
        st.success(st.session_state['success_msg'])
        st.session_state['success_msg'] = None
    if st.session_state.get('warning_msg'):
        st.warning(st.session_state['warning_msg'])
        st.session_state['warning_msg'] = None

    with st.container():
        col1, col2 = st.columns(2)
        with col1:
            st.date_input("Date", datetime.now(), key='date')
        with col2:
            st.selectbox("Category", ["Running", "Cycling", "Swimming", "Gym", "Stretching"], key='category')

        with st.form("workout_form"):
            cat = st.session_state.category
            st.subheader(f"Enter {cat} Details")
            
            # Sub-types
            is_interval = False
            if cat == "Running":
                st.selectbox("Run Type", ["Easy Run", "Long Run", "Workout"], key='subtype_run')
                if st.session_state.subtype_run == "Workout": is_interval = True
            elif cat == "Cycling":
                st.selectbox("Ride Type", ["Easy Spin", "Long Ride", "Workout"], key='subtype_ride')
                if st.session_state.subtype_ride == "Workout": is_interval = True
            
            if is_interval:
                st.markdown("##### ⏱️ Interval Structure")
                st.text_area("Breakdown", height=100, key="structure_input")
                st.write("---")

            col_dur, col_rpe = st.columns([1, 1])
            with col_dur:
                st.number_input("Total Duration (minutes)", min_value=1, key='duration')
            with col_rpe:
                st.slider("RPE", 1, 10, 5, key='rpe')
            
            if cat == "Running":
                col_d, col_p = st.columns(2)
                with col_d: st.number_input("Distance (km)", min_value=0.0, step=0.01, key='distance')
                with col_p:
                    st.checkbox("Manual Pace?", key='manual_pace')
                    if st.session_state.manual_pace:
                        st.text_input("Pace", key='pace_input')
                    else:
                        d = st.session_state.get('distance', 0)
                        t = st.session_state.get('duration', 30)
                        if d > 0:
                            mins = int(t/d)
                            secs = int(((t/d)-mins)*60)
                            st.info(f"Calc: {mins}:{secs:02d} /km")

            elif cat == "Cycling":
                col_d, col_p = st.columns(2)
                with col_d: st.number_input("Distance (km)", step=0.1, key='distance_cycle') 
                with col_p:
                    d, t = st.session_state.get('distance_cycle',0), st.session_state.get('duration',30)
                    if d>0 and t>0: st.info(f"Calc: {d/(t/60):.1f} km/h")

            elif cat == "Swimming":
                st.number_input("Distance (km)", step=0.01, key='distance_swim')

            st.text_area("Notes", key='notes')
            st.write("---")
            st.checkbox("☑️ Ready to Save?", key='confirm_save')
            st.form_submit_button("Save to Cloud", on_click=save_workout_callback)

elif page == "Dashboard":
    st.title("📊 Fitness Dashboard")
    df = load_data()
    if df.empty:
        st.warning("No data found in Cloud. Log a workout!")
    else:
        kpi1, kpi2, kpi3 = st.columns(3)
        # Week logic
        current_week_start = pd.Timestamp.now() - pd.to_timedelta(pd.Timestamp.now().dayofweek, unit='D')
        # Ensure date is comparable
        df['date'] = pd.to_datetime(df['date'])
        this_week_df = df[df['date'] >= current_week_start.normalize()]
        
        kpi1.metric("Total Workouts", len(df))
        kpi2.metric("This Week Duration", f"{this_week_df['duration_min'].sum()} min")
        kpi3.metric("This Week Distance", f"{this_week_df['distance_km'].sum():.2f} km")
        st.markdown("---")
        
        col_header, col_filter = st.columns([3, 1])
        with col_header: st.subheader("Weekly Volume (Last 12 Weeks)")
        with col_filter:
            activity_filter = st.selectbox("Filter Activity", ["All Activities"] + list(df['category'].unique()))

        if activity_filter == "All Activities":
            df_filtered = df.copy()
            c_color = '#FF4B4B'
        else:
            df_filtered = df[df['category'] == activity_filter].copy()
            colors = {"Running": "#1f77b4", "Cycling": "#ff7f0e", "Swimming": "#2ca02c", "Gym": "#9467bd", "Stretching": "#e377c2"}
            c_color = colors.get(activity_filter, '#FF4B4B')

        df_weekly = df_filtered.set_index('date').resample('W-MON')[['duration_min']].sum().reset_index()
        last_12 = pd.Timestamp.now() - pd.Timedelta(weeks=12)
        df_viz = df_weekly[df_weekly['date'] >= last_12]

        if not df_viz.empty:
            chart = alt.Chart(df_viz).mark_bar(color=c_color).encode(
                x=alt.X('date', format='%b %d', title='Week Starting'),
                y=alt.Y('duration_min', title='Minutes'),
                tooltip=['date', 'duration_min']
            ).properties(height=400)
            st.altair_chart(chart, use_container_width=True)

        st.subheader("All Time Breakdown")
        df_pie = df.groupby('category', as_index=False)['duration_min'].sum()
        pie = alt.Chart(df_pie).mark_arc(innerRadius=50).encode(
            theta=alt.Theta("duration_min"),
            color="category",
            tooltip=['category', 'duration_min']
        )
        st.altair_chart(pie, use_container_width=True)

elif page == "History / Edit":
    st.title("🗃️ History (Cloud)")
    df = load_data()
    if not df.empty:
        df['date'] = df['date'].dt.date
        cols = ['id', 'date', 'category', 'sub_type', 'distance_km', 'duration_min', 'pace', 'rpe', 'structure', 'notes']
        # Handle missing columns safely
        for c in cols: 
            if c not in df.columns: df[c] = None
            
        st.dataframe(df[cols].sort_values(by='date', ascending=False), use_container_width=True)
        st.markdown("---")
        
        st.write("To delete, copy the long ID from the table above.")
        del_id = st.text_input("Enter ID to delete") # Firestore IDs are text, not numbers
        if st.button("Delete Workout"):
            if del_id:
                delete_workout(del_id)
                st.success("Deleted!")
                st.rerun()