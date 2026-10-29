import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import create_engine, text

DB_NAME = "EmployeeDB"
DB_USER = "postgres"
DB_PASSWORD = "YOUR_PASSWORD"
DB_HOST = "localhost"
DB_PORT = "5432"

st.set_page_config(page_title="KLB Employee Dashboard", layout="wide")

# create cached app engine
@st.cache_resource
def get_engine():
    return create_engine(
        f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )

# query helper
@st.cache_data(ttl=600)
def run_query(sql, params=None):
    with get_engine().connect() as conn:
        return pd.read_sql(text(sql), conn, params=params)

st.title("KLB: Employee Dashboard")

# sidebar filters
all_divisions = run_query("SELECT divtype FROM public.divisions ORDER BY divtype")["divtype"].tolist()
all_departments = run_query("SELECT departmentname FROM public.departments ORDER BY departmentname;")["departmentname"].tolist()
min_salary = run_query("SELECT MIN(salary) AS min_salary FROM public.employeedetails")["min_salary"][0].astype("float64")
max_salary = run_query("SELECT MAX(salary) AS max_salary FROM public.employeedetails")["max_salary"][0].astype("float64")

st.sidebar.header("Filters")
chosen_divisions = st.sidebar.multiselect("Divisions", all_divisions, default=all_divisions)
chosen_departments = st.sidebar.selectbox("Employee Department", ["All"] + all_departments)
start_salary, end_salary = st.sidebar.slider("Salary", min_value = min_salary, max_value = max_salary, value = (min_salary, max_salary))

if not chosen_divisions:
    st.warning("Pick at least one division in the sidebar.")
    st.stop()

# filter for all queries
FILTER_SQL = """
    FROM public.divisions AS v
    JOIN public.employeedetails AS e ON e.divisionid = v.divisionid
    JOIN public.departments AS d ON d.departmentid = e.departmentid
    JOIN public.personaldetails AS p ON p.ssn = e.ssn
    JOIN public.jobtitles AS t ON t.jobtitleid = e.jobtitleid
    WHERE v.divtype = ANY(:divisions)
      AND (:dep = 'All' OR d.departmentname = :dep)
      AND e.salary >= :minsal AND e.salary <= :maxsal
"""
params = {"divisions": chosen_divisions, "dep": chosen_departments, "minsal": float(start_salary), "maxsal": float(end_salary)}

# KPI row
kpi = run_query(
    "SELECT DISTINCT COUNT(*) AS employees, COALESCE(AVG(e.salary), 2) AS average, "
    "PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY e.salary) AS median " + FILTER_SQL,
    params,
)
c1, c2, c3 = st.columns(3)
c1.metric("Employees", f"{kpi.loc[0, 'employees']:,}")
c2.metric("Average Salary", f"${kpi.loc[0, 'average']:,.2f}")
c3.metric("Median Salary", f"${kpi.loc[0, 'median']:,.2f}")

left, right = st.columns(2)

# employee by department bar chart
by_department = run_query(
    "SELECT d.departmentname, COUNT(e.emp_id) AS emp_count " + FILTER_SQL +
    " GROUP BY d.departmentname;",
    params,
)
with left:
    st.subheader("Headcount by department")
    if by_department.empty:
        st.info("No employees match these filters.")
    else:
        fig = px.bar(by_department, x="emp_count", y="departmentname", orientation="h",
                     labels={"emp_count": "Headcount", "departmentname": ""})
        fig.update_layout(yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig, width="stretch")

# salary box plot
salaries = run_query("SELECT v.divtype, e.salary " + FILTER_SQL + ";", params)
with right:
    st.subheader("Salary by division")
    if not salaries.empty:
        fig = px.box(salaries, x="divtype", y="salary", points="outliers",
                     labels={"divtype": "", "salary": "Salary ($)"})
        st.plotly_chart(fig, width="stretch")

# age bar chart
by_age = run_query("""
    SELECT
       CASE WHEN CURRENT_DATE - p.birthdate < 30*365 THEN 'Under 30'
           WHEN CURRENT_DATE - p.birthdate < 40*365 THEN '30-39'
           WHEN CURRENT_DATE - p.birthdate < 50*365 THEN '40-49'
           WHEN CURRENT_DATE - p.birthdate < 60*365 THEN '50-59'
           ELSE '60+'
       END AS age_category, AVG(e.salary) AS avg_salary, COUNT(e.emp_id) AS emp_count""" + FILTER_SQL +
    """GROUP BY
       CASE WHEN CURRENT_DATE - p.birthdate < 30*365 THEN 'Under 30'
           WHEN CURRENT_DATE - p.birthdate < 40*365 THEN '30-39'
           WHEN CURRENT_DATE - p.birthdate < 50*365 THEN '40-49'
           WHEN CURRENT_DATE - p.birthdate < 60*365 THEN '50-59'
           ELSE '60+'
       END;""",
    params,
)
with left:
    st.subheader("Headcount by age")
    if by_age.empty:
        st.info("No employees match these filters.")
    else:
        fig = px.bar(by_age, x="avg_salary", y="age_category", text="emp_count", orientation="h",
                     labels={"avg_salary": "Average Salary ($)", "age_category": ""})
        fig.update_layout(yaxis={"categoryorder": "array", "categoryarray": ["60+", "50-59", "40-49", "30-39", "Under 30"]})
        st.plotly_chart(fig, width="stretch")

# highest title salaries
by_title = run_query("""
    SELECT t.jobtitle, AVG(e.salary) AS salary""" + FILTER_SQL + """
    GROUP BY t.jobtitle
    ORDER BY AVG(e.salary) DESC LIMIT 10;""",
    params,
)
with right:
    st.subheader("Top titles by salary")
    if by_title.empty:
        st.info("No employees match these filters.")
    else:
        fig = px.bar(by_title, x="salary", y="jobtitle", orientation="h",
                     labels={"salary": "Salary ($)", "jobtitle": ""})
        fig.update_layout(yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig, width="stretch")

# employee table
employees = run_query("""
    SELECT p.name, t.jobtitle, d.departmentname, v.divtype, e.salary""" + FILTER_SQL + """
    ORDER BY e.salary DESC;""", params,
)
st.subheader("Employee table")
if employees.empty:
    st.info("No employees match these filters.")
else:
    with st.expander("View employees"):
        st.dataframe(employees, column_config={"name": "Name", "jobtitle": "Job Title",
                                               "departmentname": "Department", "divtype": "Division",
                                               "salary": "Salary"}, hide_index=True)