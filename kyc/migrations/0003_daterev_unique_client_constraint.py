from django.db import migrations, models


def dedupe_daterev_by_client(apps, schema_editor):
    daterev_model = apps.get_model("kyc", "DATEREV")
    table = schema_editor.connection.ops.quote_name(daterev_model._meta.db_table)
    sql = f"""
    DELETE FROM {table}
    WHERE id IN (
        SELECT id
        FROM (
            SELECT
                id,
                ROW_NUMBER() OVER (
                    PARTITION BY CLIENT
                    ORDER BY
                        CASE WHEN DATEREV IS NULL THEN 1 ELSE 0 END,
                        DATEREV DESC,
                        id DESC
                ) AS rn
            FROM {table}
            WHERE CLIENT IS NOT NULL AND CLIENT <> ''
        ) t
        WHERE t.rn > 1
    )
    """
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(sql)


DATEREV_CLIENT_UNIQUE_CONSTRAINT = models.UniqueConstraint(
    fields=("CLIENT",),
    condition=models.Q(CLIENT__gt=""),
    name="uniq_daterev_client_non_empty",
)


def add_daterev_client_unique_constraint(apps, schema_editor):
    daterev_model = apps.get_model("kyc", "DATEREV")
    vendor = schema_editor.connection.vendor
    table_name = daterev_model._meta.db_table
    table = schema_editor.connection.ops.quote_name(table_name)
    client_col = schema_editor.connection.ops.quote_name("CLIENT")
    index_name = "uniq_daterev_client_non_empty"
    q_index_name = schema_editor.connection.ops.quote_name(index_name)

    if vendor in {"microsoft", "sql_server"}:
        with schema_editor.connection.cursor() as cursor:
            cursor.execute(
                f"""
                IF NOT EXISTS (
                    SELECT 1
                    FROM sys.indexes
                    WHERE name = N'{index_name}'
                      AND object_id = OBJECT_ID(N'{table_name}')
                )
                CREATE UNIQUE INDEX {q_index_name}
                    ON {table} ({client_col})
                    WHERE {client_col} IS NOT NULL AND {client_col} <> '';
                """
            )
        return

    schema_editor.add_constraint(daterev_model, DATEREV_CLIENT_UNIQUE_CONSTRAINT)


def remove_daterev_client_unique_constraint(apps, schema_editor):
    daterev_model = apps.get_model("kyc", "DATEREV")
    vendor = schema_editor.connection.vendor
    table_name = daterev_model._meta.db_table
    table = schema_editor.connection.ops.quote_name(table_name)
    index_name = "uniq_daterev_client_non_empty"
    q_index_name = schema_editor.connection.ops.quote_name(index_name)

    if vendor in {"microsoft", "sql_server"}:
        with schema_editor.connection.cursor() as cursor:
            cursor.execute(
                f"""
                IF EXISTS (
                    SELECT 1
                    FROM sys.indexes
                    WHERE name = N'{index_name}'
                      AND object_id = OBJECT_ID(N'{table_name}')
                )
                DROP INDEX {q_index_name} ON {table};
                """
            )
        return

    schema_editor.remove_constraint(daterev_model, DATEREV_CLIENT_UNIQUE_CONSTRAINT)


class Migration(migrations.Migration):

    dependencies = [
        ("kyc", "0002_replace_agents_with_user"),
    ]

    operations = [
        migrations.RunPython(dedupe_daterev_by_client, migrations.RunPython.noop),
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(
                    add_daterev_client_unique_constraint,
                    remove_daterev_client_unique_constraint,
                )
            ],
            state_operations=[
                migrations.AddConstraint(
                    model_name="daterev",
                    constraint=DATEREV_CLIENT_UNIQUE_CONSTRAINT,
                )
            ],
        ),
    ]
