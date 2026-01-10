from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='marketplace',
            field=models.CharField(
                choices=[
                    ('amazon', 'Amazon'),
                    ('ebay', 'Ebay'),
                    ('etsy', 'Etsy'),
                    ('fankultur', 'Fankultur Seite'),
                    ('unbekannt', 'Unbekannt'),
                ],
                default='unbekannt',
                max_length=30,
            ),
        ),
    ]
