# Generated by Django 3.2.13 on 2022-07-06 11:36

from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('wagtailcore', '0066_collection_management_permissions'),
        ('wagtailpages', '0036_auto_20220706_1130'),
    ]

    operations = [
        migrations.AlterField(
            model_name='blogauthors',
            name='locale',
            field=models.ForeignKey(editable=False, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='wagtailcore.locale'),
        ),
        migrations.AlterField(
            model_name='blogauthors',
            name='translation_key',
            field=models.UUIDField(default=uuid.uuid4, editable=False),
        ),
        migrations.AlterUniqueTogether(
            name='blogauthors',
            unique_together={('translation_key', 'locale')},
        ),
    ]
