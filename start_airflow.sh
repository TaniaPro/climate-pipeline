#!/bin/bash
REPO="$(cd "$(dirname "$0")" && pwd)"

source ~/airflow-venv/bin/activate
export AIRFLOW__CORE__DAGS_FOLDER="$REPO/dags"
export AIRFLOW__CORE__LOAD_EXAMPLES=False
airflow standalone