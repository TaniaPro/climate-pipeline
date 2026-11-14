import pendulum
from airflow.sdk import DAG
from airflow.providers.standard.operators.bash import BashOperator

PROJECT = "/Users/taniaprosku/Projects/climate-pipeline"

with DAG(
    dag_id="climate_daily",
    schedule="@daily",
    start_date=pendulum.datetime(2026, 11, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
) as dag:

    load_observations = BashOperator(
        task_id="load_observations",
        bash_command=(
            f"cd {PROJECT} && .venv/bin/python -u -c "
            "'from ingestion_pipeline_run import run_observations_pipeline; "
            "run_observations_pipeline(daily=True)'"
        ),
    )

    dbt_run = BashOperator(
        task_id="dbt_run",
        bash_command=f"cd {PROJECT}/climate_dbt && ../.venv/bin/dbt run",
    )

    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command=f"cd {PROJECT}/climate_dbt && ../.venv/bin/dbt test",
    )

    load_observations >> dbt_run >> dbt_test