# Generated by Django 3.2.13 on 2022-08-09 11:47

from django.db import migrations, models
import modelcluster.fields


class Migration(migrations.Migration):

    dependencies = [
        ('wagtailpages', '0040_alter_blogpage_topics'),
    ]

    operations = [
        migrations.AlterField(
            model_name='blogindexpage',
            name='related_topics',
            field=modelcluster.fields.ParentalManyToManyField(blank=True, help_text='Which topics would you like to feature on the page? Please select a max of 7.', limit_choices_to=models.Q(('locale__id', '1')), to='wagtailpages.BlogPageTopic'),
        ),
    ]
