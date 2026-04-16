# Migration Phase 3 - enrichissements pour contraintes molles + poids ajustables
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0002_alter_shiftrequiredcertification_unique_together_and_more'),
    ]

    operations = [
        # ── M1 : limite de nuits consécutives par type de contrat ──────────
        migrations.AddField(
            model_name='contracttype',
            name='max_consecutive_nights',
            field=models.IntegerField(default=3),
        ),

        # ── M7 : flag continuité de soins activée sur le service ──────────
        migrations.AddField(
            model_name='service',
            name='requires_care_continuity',
            field=models.BooleanField(default=False),
        ),

        # ── M2 : enrichissement de Preference pour typage structuré ───────
        migrations.AddField(
            model_name='preference',
            name='kind',
            field=models.CharField(
                max_length=32,
                default='free_text',
                choices=[
                    ('wants_shift_type',  'Veut ce type de garde'),
                    ('avoids_shift_type', 'Veut éviter ce type de garde'),
                    ('wants_day',         'Veut ce jour de la semaine'),
                    ('avoids_day',        'Veut éviter ce jour de la semaine'),
                    ('wants_service',     'Veut ce service'),
                    ('avoids_service',    'Veut éviter ce service'),
                    ('free_text',         'Contrainte texte libre (Phase 2)'),
                ],
            ),
        ),
        migrations.AddField(
            model_name='preference',
            name='importance',
            field=models.IntegerField(default=1),
        ),
        migrations.AddField(
            model_name='preference',
            name='target_shift_type',
            field=models.ForeignKey(
                null=True, blank=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='preferences',
                to='api.shifttype',
            ),
        ),
        migrations.AddField(
            model_name='preference',
            name='target_service',
            field=models.ForeignKey(
                null=True, blank=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='preferences',
                to='api.service',
            ),
        ),
        migrations.AddField(
            model_name='preference',
            name='target_day_of_week',
            field=models.IntegerField(null=True, blank=True),
        ),

        # ── Poids ajustables des contraintes molles ───────────────────────
        migrations.CreateModel(
            name='SoftConstraintWeight',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=32, unique=True)),
                ('weight', models.FloatField()),
                ('description', models.CharField(blank=True, max_length=255)),
            ],
        ),
    ]
