# Generated by Django 3.1.11 on 2021-05-31 17:37

from django.db import migrations
from wagtail.core.models import BootstrapTranslatableModel


class Migration(migrations.Migration):

    dependencies = [
        ("news", "0005_auto_20210531_1735"),
    ]

    operations = [BootstrapTranslatableModel("news.News")]
