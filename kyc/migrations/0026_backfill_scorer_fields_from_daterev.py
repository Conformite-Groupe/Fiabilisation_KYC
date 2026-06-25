from django.db import migrations


def backfill_scorer_fields(apps, schema_editor):
    KycPp = apps.get_model("kyc", "Kyc_pp")
    KycPm = apps.get_model("kyc", "Kyc_pm")
    DateRev = apps.get_model("kyc", "DATEREV")

    pp_table = KycPp._meta.db_table
    pm_table = KycPm._meta.db_table
    daterev_table = DateRev._meta.db_table
    vendor = schema_editor.connection.vendor

    with schema_editor.connection.cursor() as cursor:
        if vendor == "sqlite":
            cursor.execute(f"""
                UPDATE {pp_table} AS pp
                SET
                    DATEREV = COALESCE(CAST(d.DATEREV AS TEXT), pp.DATEREV, ''),
                    RISQUE = COALESCE(d.RISQUE, pp.RISQUE, '')
                FROM {daterev_table} AS d
                WHERE pp.CLIENT <> ''
                  AND d.CLIENT = pp.CLIENT
            """)
            cursor.execute(f"""
                UPDATE {pm_table} AS pm
                SET
                    DATEREV = COALESCE(CAST(d.DATEREV AS TEXT), pm.DATEREV, ''),
                    PPE = COALESCE(d.PPE, pm.PPE, ''),
                    RISQUE = COALESCE(d.RISQUE, pm.RISQUE, '')
                FROM {daterev_table} AS d
                WHERE pm.CLIENT <> ''
                  AND d.CLIENT = pm.CLIENT
            """)
            return

        if vendor in {"microsoft", "mssql", "sql_server"}:
            cursor.execute(f"""
                UPDATE pp
                SET
                    pp.DATEREV = COALESCE(CONVERT(varchar(10), d.DATEREV, 23), pp.DATEREV, ''),
                    pp.RISQUE = COALESCE(d.RISQUE, pp.RISQUE, '')
                FROM {pp_table} pp
                INNER JOIN {daterev_table} d ON d.CLIENT = pp.CLIENT
                WHERE pp.CLIENT <> ''
            """)
            cursor.execute(f"""
                UPDATE pm
                SET
                    pm.DATEREV = COALESCE(CONVERT(varchar(10), d.DATEREV, 23), pm.DATEREV, ''),
                    pm.PPE = COALESCE(d.PPE, pm.PPE, ''),
                    pm.RISQUE = COALESCE(d.RISQUE, pm.RISQUE, '')
                FROM {pm_table} pm
                INNER JOIN {daterev_table} d ON d.CLIENT = pm.CLIENT
                WHERE pm.CLIENT <> ''
            """)
            return

        cursor.execute(f"""
            UPDATE {pp_table}
            SET
                DATEREV = COALESCE((
                    SELECT CAST(d.DATEREV AS varchar(20))
                    FROM {daterev_table} d
                    WHERE d.CLIENT = {pp_table}.CLIENT
                ), DATEREV, ''),
                RISQUE = COALESCE((
                    SELECT d.RISQUE
                    FROM {daterev_table} d
                    WHERE d.CLIENT = {pp_table}.CLIENT
                ), RISQUE, '')
            WHERE CLIENT <> ''
        """)
        cursor.execute(f"""
            UPDATE {pm_table}
            SET
                DATEREV = COALESCE((
                    SELECT CAST(d.DATEREV AS varchar(20))
                    FROM {daterev_table} d
                    WHERE d.CLIENT = {pm_table}.CLIENT
                ), DATEREV, ''),
                PPE = COALESCE((
                    SELECT d.PPE
                    FROM {daterev_table} d
                    WHERE d.CLIENT = {pm_table}.CLIENT
                ), PPE, ''),
                RISQUE = COALESCE((
                    SELECT d.RISQUE
                    FROM {daterev_table} d
                    WHERE d.CLIENT = {pm_table}.CLIENT
                ), RISQUE, '')
            WHERE CLIENT <> ''
        """)


class Migration(migrations.Migration):

    dependencies = [
        ("kyc", "0025_add_scorer_fields_to_kyc_models"),
    ]

    operations = [
        migrations.RunPython(backfill_scorer_fields, migrations.RunPython.noop),
    ]
