from django.contrib.auth.management import create_permissions
from django.db import migrations

GROUP_NAME = "Email inbox"
PERMISSION_CODENAME = "use_email_inbox"


def create_group(apps, schema_editor):
    # Permissions are normally created by a post-migrate signal, so they may
    # not exist yet when this data migration runs on a fresh database.
    for app_config in apps.get_app_configs():
        app_config.models_module = True
        create_permissions(app_config, apps=apps, verbosity=0)
        app_config.models_module = None

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    group, _ = Group.objects.get_or_create(name=GROUP_NAME)
    permission = Permission.objects.get(
        codename=PERMISSION_CODENAME,
        content_type__app_label="task_processor",
    )
    group.permissions.add(permission)


def delete_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name=GROUP_NAME).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("task_processor", "0016_emailinbox_allowedsender"),
        ("auth", "__first__"),
        ("contenttypes", "__first__"),
    ]

    operations = [
        migrations.RunPython(create_group, delete_group),
    ]
