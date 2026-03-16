import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('services', '0006_projectextramaterial'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProjectItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('item_name', models.CharField(max_length=200)),
                ('item_type', models.CharField(choices=[('Task', 'Task'), ('Material', 'Material'), ('Tool', 'Tool')], max_length=20)),
                ('quantity', models.PositiveIntegerField(default=1)),
                ('unit_cost', models.DecimalField(decimal_places=2, max_digits=10)),
                ('extra_cost', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ('is_optional', models.BooleanField(default=False)),
                ('display_order', models.PositiveIntegerField(default=0)),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='project_items', to='services.project')),
                ('service_item', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='project_items', to='services.serviceitem')),
            ],
            options={
                'ordering': ['display_order'],
            },
        ),
    ]
