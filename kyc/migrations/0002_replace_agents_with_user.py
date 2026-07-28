from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def forwards_map_agents(apps, schema_editor):
    Agents = apps.get_model("kyc", "Agents")
    Notation = apps.get_model("kyc", "Notation")
    Historique = apps.get_model("kyc", "Historique")
    Compte = apps.get_model("kyc", "Compte")

    app_label, model_name = settings.AUTH_USER_MODEL.split(".")
    User = apps.get_model(app_label, model_name)

    users = User.objects.all().only("id", "username", "email", "code_expl")
    by_username = {u.username.lower(): u.id for u in users if u.username}
    by_email = {u.email.lower(): u.id for u in users if u.email}
    by_code = {u.code_expl: u.id for u in users if getattr(u, "code_expl", "")}

                                          
    placeholder_user = None

    def get_placeholder_user():
        nonlocal placeholder_user
        if placeholder_user is not None:
            return placeholder_user
        placeholder_username = "placeholder@kyc.local"
        placeholder_email = "placeholder@kyc.local"
        obj, _ = User.objects.get_or_create(
            username=placeholder_username,
            defaults={
                "email": placeholder_email,
                "first_name": "Placeholder",
                "last_name": "Agent",
                "is_active": False,
            },
        )
        placeholder_user = obj
        return placeholder_user

    def map_agent_to_user(agent):
        if agent is None:
            return None
        email = (agent.email or "").strip().lower()
        if email and email in by_username:
            return by_username[email]
        if email and email in by_email:
            return by_email[email]
        expl = (agent.expl or "").strip()
        if expl and expl in by_code:
            return by_code[expl]
        return get_placeholder_user().id

              
    for obj in Notation.objects.select_related("agent").all():
        user_id = map_agent_to_user(obj.agent)
        if user_id:
            obj.agent_user_id = user_id
            obj.save(update_fields=["agent_user"])

                
    for obj in Historique.objects.select_related("agent").all():
        user_id = map_agent_to_user(obj.agent)
        if user_id:
            obj.agent_user_id = user_id
            obj.save(update_fields=["agent_user"])

            
    for obj in Compte.objects.select_related("agent").all():
        user_id = map_agent_to_user(obj.agent)
        if user_id:
            obj.agent_user_id = user_id
            obj.save(update_fields=["agent_user"])


class Migration(migrations.Migration):

    dependencies = [
        ("kyc", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="notation",
            name="agent_user",
            field=models.ForeignKey(
                to=settings.AUTH_USER_MODEL,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="notations_tmp",
            ),
        ),
        migrations.AddField(
            model_name="historique",
            name="agent_user",
            field=models.ForeignKey(
                to=settings.AUTH_USER_MODEL,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="historiques_tmp",
            ),
        ),
        migrations.AddField(
            model_name="compte",
            name="agent_user",
            field=models.ForeignKey(
                to=settings.AUTH_USER_MODEL,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="comptes_tmp",
            ),
        ),
        migrations.RunPython(forwards_map_agents, migrations.RunPython.noop),
        migrations.RemoveField(model_name="notation", name="agent"),
        migrations.RemoveField(model_name="historique", name="agent"),
        migrations.RemoveField(model_name="compte", name="agent"),
        migrations.RenameField(model_name="notation", old_name="agent_user", new_name="agent"),
        migrations.RenameField(model_name="historique", old_name="agent_user", new_name="agent"),
        migrations.RenameField(model_name="compte", old_name="agent_user", new_name="agent"),
        migrations.AlterField(
            model_name="notation",
            name="agent",
            field=models.ForeignKey(
                to=settings.AUTH_USER_MODEL,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="notations",
            ),
        ),
        migrations.AlterField(
            model_name="historique",
            name="agent",
            field=models.ForeignKey(
                to=settings.AUTH_USER_MODEL,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="historiques",
            ),
        ),
        migrations.AlterField(
            model_name="compte",
            name="agent",
            field=models.ForeignKey(
                to=settings.AUTH_USER_MODEL,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="comptes",
            ),
        ),
        migrations.DeleteModel(name="Agents"),
    ]
