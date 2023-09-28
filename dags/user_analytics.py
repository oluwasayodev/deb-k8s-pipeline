from airflow import DAG
from datetime import datetime
from airflow.operators.python import PythonOperator
from airflow.operators.empty import EmptyOperator
from airflow.providers.postgres.operators.postgres import PostgresOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.providers.google.cloud.hooks.gcs import GCSHook
from airflow.providers.google.cloud.sensors.gcs import GCSObjectExistenceSensor
from airflow.utils.dates import days_ago
from airflow.utils.trigger_rule import TriggerRule
from airflow.providers.common.sql.operators.sql import BranchSQLOperator

GCP_CONN_ID = "gcp_airflow_conn"
GCS_BUCKET_NAME = "wizeline-sayo-bucket"
GCS_USERS_KEY_NAME = "user_purchase/user_purchase.csv"

POSTGRES_CONN_ID = "capstone_postgres_db"
POSTGRES_SCHEMA_NAME = 'ecommerce'
POSTGRES_TABLE_NAME = "user_purchase"


def ingest_data_from_gcs(
    gcs_bucket: str,
    gcs_object: str,
    postgres_table: str,
    gcp_conn_id: str,
    postgres_conn_id: str,
):
    import tempfile

    gcs_hook = GCSHook(gcp_conn_id=gcp_conn_id)
    psql_hook = PostgresHook(postgres_conn_id=postgres_conn_id)

    with tempfile.NamedTemporaryFile() as tmp:
        gcs_hook.download(bucket_name=gcs_bucket, object_name=gcs_object)
        psql_hook.bulk_load(table=postgres_table, tmp_file=tmp.name)


with DAG(
    "user_analytics",
    start_date=days_ago(1),
    schedule="@once",
    description="A DAG to loadcsv to cloud sql",
    catchup=False,
) as dag:
    start_workflow = EmptyOperator(task_id="start_workflow")

    verify_existence = GCSObjectExistenceSensor(
        task_id="verify_existence",
        google_cloud_conn_id=GCP_CONN_ID,
        bucket=GCS_BUCKET_NAME,
        object=GCS_USERS_KEY_NAME,
    )

    create_schema = PostgresOperator(
        task_id="create_schema",
        postgres_conn_id=POSTGRES_CONN_ID,
        sql="CREATE SCHEMA IF NOT EXISTS {SCHEMA_NAME};".format(SCHEMA_NAME=POSTGRES_SCHEMA_NAME),
    )

    create_table_entity = PostgresOperator(
        task_id="create_table_entity",
        postgres_conn_id=POSTGRES_CONN_ID,
        sql="""
        CREATE TABLE IF NOT EXISTS {SCHEMA_NAME}.{TABLE_NAME} (
            invoice_no VARCHAR(10),
            stock_code VARCHAR(20),
            description VARCHAR(1000),
            quantity INT,
            invoice_date TIMESTAMP,
            unit_price NUMERIC(8, 3),
            customer_id VARCHAR(20),
            country VARCHAR(20)
        );
        """.format(SCHEMA_NAME=POSTGRES_SCHEMA_NAME, TABLE_NAME=POSTGRES_TABLE_NAME),
    )

    clear_table = PostgresOperator(
        task_id="clear_table",
        postgres_conn_id=POSTGRES_CONN_ID,
        sql="DELETE FROM {TABLE_NAME}".format(TABLE_NAME=POSTGRES_TABLE_NAME),
    )

    continue_process = EmptyOperator(task_id='continue_process')

    ingest_data = PythonOperator(
        task_id='ingest_data',
        python_callable=ingest_data_from_gcs,
        op_kwargs={
            "gcp_conn_id": GCP_CONN_ID,
            "postgres_conn_id": POSTGRES_CONN_ID,
            "gcs_bucket": GCS_BUCKET_NAME,
            "gcs_object": GCS_USERS_KEY_NAME
        },
        trigger_rule=TriggerRule.ONE_SUCCESS
    )

    validate_data = BranchSQLOperator(
        task_id="validate_data",
        conn_id=GCP_CONN_ID,
        sql="SELECT COUNT(*) AS total_rows FROM {SCHEMA_NAME}.{TABLE_NAME}".format(SCHEMA_NAME=POSTGRES_SCHEMA_NAME, TABLE_NAME=POSTGRES_TABLE_NAME),
        follow_task_ids_if_false=[continue_process.task_id],
        follow_task_ids_if_true=[clear_table.task_id],
    )


    end_workflow = EmptyOperator(task_id='end_workflow')


    start_workflow >> verify_existence >> create_schema >> create_table_entity

    create_table_entity >> validate_data >> [clear_table, continue_process] >> ingest_data

    ingest_data >> end_workflow