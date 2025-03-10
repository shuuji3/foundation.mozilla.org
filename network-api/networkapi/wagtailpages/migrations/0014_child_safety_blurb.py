# Generated by Django 3.2.13 on 2022-04-13 01:56

import wagtail.core.fields
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("wagtailpages", "0013_article_hero_custom_coloring"),
    ]

    operations = [
        migrations.AddField(
            model_name="generalproductpage",
            name="child_safety_blurb",
            field=wagtail.core.fields.RichTextField(
                blank=True,
                help_text="Child safety information, if applicable.",
                max_length=5000,
            ),
        ),
    ]
