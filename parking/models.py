from django.contrib.auth.models import User
from django.db import models
from django.db.models import Q
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse


class EOSAccount(models.Model):
    user = models.OneToOneField(User, related_name="a", on_delete=models.CASCADE)

    # TODO
    # 1) private_key TextField
    #    default should prob be a method that generates private key.
    #    Should later call eos api to create eos account in post_save
    #    for reference: https://stackoverflow.com/questions/16216363/how-can-you-store-a-rsa-key-pair-in-a-django-model-sqlite-db
    #
    # 2) possibly other fields including account and a second key
    #
    # Should add any new manually entered fields to REQUIRED_FIELDS

    # TODO find out precision and decide on default
    balance = models.DecimalField(default=1000.0, max_digits=20, decimal_places=10)
    minimum_balance = models.DecimalField(default=0.0, max_digits=20, decimal_places=10)

    def __str__(self):
        return str(self.user)

    def net_balance(self):
        return self.balance - self.minimum_balance

    def owns(self, spot, start, end):
        return Future.objects.filter(spot=spot).owned_by(self, start, end).exists()

    def owns(self, start, end):
        return Future.objects.owned_by(self, start, end).values_list("spot", flat=True)


class Group(models.Model):
    name = models.CharField(max_length=50)
    creator = models.ForeignKey(
        EOSAccount, related_name="owned_groups", on_delete=models.CASCADE
    )
    members = models.ManyToManyField(EOSAccount, related_name="+")
    Fee = models.DecimalField(max_digits=20, decimal_places=10)
    minimum_price = models.DecimalField(max_digits=20, decimal_places=10)
    minimum_ratio = models.DecimalField(max_digits=3, decimal_places=2)

    def __str__(self):
        return self.name


class Lot(models.Model):
    name = models.CharField(max_length=50)

    def __str__(self):
        return self.name


class Spot(models.Model):
    lot = models.ForeignKey(Lot, related_name="spots", on_delete=models.CASCADE)
    number = models.IntegerField()

    class Meta:
        unique_together = [["lot", "number"]]

    def __str__(self):
        return "{} | {}".format(self.lot.name, self.number)


class FutureQuerySet(models.QuerySet):
    def owned_by(self, a, start, end):
        sales = self.filter(seller=a, buyer__isnull=False).filter(
            Q(start_time__gte=start, start_time__lte=end)
            | Q(end_time__gte=start, end_time__lte=end)
            | Q(start_time__lte=start, end_time__gte=end),
        )

        return self.filter(
            start_time__lte=start, end_time__gte=end, buyer=a, seller__isnull=False,
        ).exclude(id__in=sales)


class Future(models.Model):
    buyer = models.ForeignKey(
        EOSAccount, related_name="+", null=True, blank=True, on_delete=models.CASCADE
    )
    seller = models.ForeignKey(
        EOSAccount, related_name="+", null=True, blank=True, on_delete=models.CASCADE
    )
    lot = models.ForeignKey(Lot, on_delete=models.CASCADE)
    spot = models.ForeignKey(Spot, null=True, blank=True, on_delete=models.CASCADE)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField(blank=True)
    request_expiration_time = models.DateTimeField()
    price = models.DecimalField(max_digits=20, decimal_places=10)
    group = models.ForeignKey(
        Group, related_name="+", null=True, blank=True, on_delete=models.CASCADE
    )

    objects = FutureQuerySet.as_manager()

    def get_absolute_url(self):
        # TODO account for different link for purchases to specify group
        return reverse("future_transact", args=[self.pk])


class Option(Future):
    fee = models.DecimalField(max_digits=20, decimal_places=10)
    collateral = models.DecimalField(max_digits=20, decimal_places=10)


@receiver(post_save, sender=User, dispatch_uid="create_user_eos_account")
def create_user_eos_account(sender, instance, created, **kwargs):
    if created:
        EOSAccount.objects.create(user=instance)