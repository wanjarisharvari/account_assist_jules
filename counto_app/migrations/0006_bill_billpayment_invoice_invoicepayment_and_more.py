# Generated by Django 4.2.7 on 2025-05-22 10:09

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        (
            "counto_app",
            "0005_remove_transaction_amount_remove_transaction_party_and_more",
        ),
    ]

    operations = [
        migrations.CreateModel(
            name="Bill",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("bill_number", models.CharField(max_length=50)),
                ("date", models.DateField()),
                ("due_date", models.DateField(blank=True, null=True)),
                ("description", models.CharField(max_length=255)),
                ("amount_due", models.DecimalField(decimal_places=2, max_digits=12)),
                (
                    "amount_paid",
                    models.DecimalField(decimal_places=2, default=0.0, max_digits=12),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name="BillPayment",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("date", models.DateField()),
                ("notes", models.TextField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name="Invoice",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("invoice_number", models.CharField(max_length=50, unique=True)),
                ("date", models.DateField()),
                ("due_date", models.DateField(blank=True, null=True)),
                ("description", models.CharField(max_length=255)),
                ("amount_due", models.DecimalField(decimal_places=2, max_digits=12)),
                (
                    "amount_received",
                    models.DecimalField(decimal_places=2, default=0.0, max_digits=12),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name="InvoicePayment",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("date", models.DateField()),
                ("notes", models.TextField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.RemoveField(
            model_name="transaction",
            name="expected_amount",
        ),
        migrations.RemoveField(
            model_name="transaction",
            name="paid_amount",
        ),
        migrations.RemoveField(
            model_name="transaction",
            name="status",
        ),
        migrations.AddField(
            model_name="customer",
            name="is_active",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="customer",
            name="total_receivable",
            field=models.DecimalField(decimal_places=2, default=0.0, max_digits=12),
        ),
        migrations.AddField(
            model_name="customer",
            name="total_received",
            field=models.DecimalField(decimal_places=2, default=0.0, max_digits=12),
        ),
        migrations.AddField(
            model_name="customer",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AddField(
            model_name="transaction",
            name="amount",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="transaction",
            name="notes",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="vendor",
            name="is_active",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="vendor",
            name="total_paid",
            field=models.DecimalField(decimal_places=2, default=0.0, max_digits=12),
        ),
        migrations.AddField(
            model_name="vendor",
            name="total_payable",
            field=models.DecimalField(decimal_places=2, default=0.0, max_digits=12),
        ),
        migrations.AddField(
            model_name="vendor",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AlterField(
            model_name="pendingtransaction",
            name="amount",
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=12, null=True
            ),
        ),
        migrations.AddIndex(
            model_name="customer",
            index=models.Index(
                fields=["user", "name"], name="counto_app__user_id_333bb0_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="customer",
            index=models.Index(
                fields=["user", "is_active"], name="counto_app__user_id_0b8dff_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="transaction",
            index=models.Index(
                fields=["user", "date"], name="counto_app__user_id_433d3b_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="transaction",
            index=models.Index(
                fields=["user", "transaction_type"],
                name="counto_app__user_id_dea07f_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="transaction",
            index=models.Index(
                fields=["user", "category"], name="counto_app__user_id_ca2766_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="transaction",
            index=models.Index(
                fields=["date", "transaction_type"], name="counto_app__date_e06221_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="vendor",
            index=models.Index(
                fields=["user", "name"], name="counto_app__user_id_7338ab_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="vendor",
            index=models.Index(
                fields=["user", "is_active"], name="counto_app__user_id_affdde_idx"
            ),
        ),
        migrations.AddField(
            model_name="invoicepayment",
            name="invoice",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="payments",
                to="counto_app.invoice",
            ),
        ),
        migrations.AddField(
            model_name="invoicepayment",
            name="transaction",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="counto_app.transaction",
            ),
        ),
        migrations.AddField(
            model_name="invoice",
            name="customer",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="invoices",
                to="counto_app.customer",
            ),
        ),
        migrations.AddField(
            model_name="invoice",
            name="user",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL
            ),
        ),
        migrations.AddField(
            model_name="billpayment",
            name="bill",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="payments",
                to="counto_app.bill",
            ),
        ),
        migrations.AddField(
            model_name="billpayment",
            name="transaction",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="counto_app.transaction",
            ),
        ),
        migrations.AddField(
            model_name="bill",
            name="user",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL
            ),
        ),
        migrations.AddField(
            model_name="bill",
            name="vendor",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="bills",
                to="counto_app.vendor",
            ),
        ),
        migrations.AddIndex(
            model_name="invoice",
            index=models.Index(
                fields=["user", "customer"], name="counto_app__user_id_db35ae_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="invoice",
            index=models.Index(
                fields=["date", "due_date"], name="counto_app__date_05f6b7_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="bill",
            index=models.Index(
                fields=["user", "vendor"], name="counto_app__user_id_fe9038_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="bill",
            index=models.Index(
                fields=["date", "due_date"], name="counto_app__date_b0ffdb_idx"
            ),
        ),
        migrations.AlterUniqueTogether(
            name="bill",
            unique_together={("user", "bill_number")},
        ),
    ]
