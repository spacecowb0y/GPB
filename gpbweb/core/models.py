# coding: utf-8

from django.db import models
from django.utils.translation import ugettext_lazy as _

from django_extensions.db import fields

from datetime import datetime
from gpbweb.postgres_fts import models as fts_models

from south.modelsinspector import add_ignored_fields

add_ignored_fields(["^gpbweb\.postgres_fts\.models\.VectorField",])


class ProveedorManager(models.Manager):

    def por_compras(self, **filter_args):

        filter_args['compra__fecha__gte'] = filter_args.get('compra__fecha__gte', datetime(datetime.now().year, datetime.now().month, 1))
        filter_args['compra__fecha__lte'] = filter_args.get('compra__fecha__lte', datetime.now())

        return self.select_related('compra_set') \
            .filter(**filter_args) \
            .annotate(total_compras=models.Sum('compra__importe')) \
            .order_by('-total_compras')

class Proveedor(models.Model):

    objects = ProveedorManager()

    nombre = models.TextField(_('Nombre'), max_length=256, null=False, blank=True, unique=True)
    cuit = models.CharField(_('CUIT'), max_length=32, null=True, blank=True)
    domicilio = models.CharField(_('Domicilio'), max_length=128, null=True, blank=True)
    localidad = models.CharField(_('Localidad'), max_length=128, null=True, blank=True)
    slug = fields.AutoSlugField(populate_from='nombre', overwrite=True)

    def __unicode__(self):
        return self.nombre

    @models.permalink
    def get_absolute_url(self):
        return ('gpbweb.core.views.proveedor', (),
                {'proveedor_slug': self.slug})


class ReparticionManager(models.Manager):
    def por_gastos(self, **filter_args):
        """ Lista de Reparticion ordenadas por la que mas gastos produjo en un período """

        filter_args['compra__fecha__gte'] = filter_args.get('compra__fecha__gte', datetime(datetime.now().year, datetime.now().month, 1))
        filter_args['compra__fecha__lte'] = filter_args.get('compra__fecha__lte', datetime.now())

        return self.select_related('compra_set') \
            .filter(**filter_args) \
            .annotate(total_compras=models.Sum('compra__importe')) \
            .order_by('-total_compras')

class Reparticion(models.Model):

    objects = ReparticionManager()

    nombre = models.CharField(_('Nombre'), max_length=128, null=False, blank=False, unique=True)
    slug = fields.AutoSlugField(populate_from='nombre', overwrite=True)

    def __unicode__(self):
        return self.nombre

    @models.permalink
    def get_absolute_url(self):
        return ('gpbweb.core.views.reparticion', (),
                {'reparticion_slug': self.slug})


class CompraManager(models.Manager):
    def total_periodo(self, fecha_desde=datetime(datetime.now().year, datetime.now().month, 1), fecha_hasta=datetime.now()):
        return self.filter(fecha__gte=fecha_desde, fecha__lte=fecha_hasta).aggregate(total=models.Sum('importe'))['total'] or 0

    # es medio hacky, pero es lo que hay
    # idea encontrada aca: http://www.caktusgroup.com/blog/2009/09/28/custom-joins-with-djangos-queryjoin/
    def search(self, query):
        c = self.extra(select={'rank': 'ts_rank_cd(core_compralineaitem.search_index, to_tsquery(\'spanish\', E\'%s\'), %d)' % (query, 32)},
                       where=["core_compralineaitem.search_index @@ to_tsquery('spanish', %s)"
                              " OR core_proveedor.search_index @@ to_tsquery('spanish', %s)"
                              " OR core_reparticion.search_index @@ to_tsquery('spanish', %s)"], 
                       params=[query, query, query])

        c.query.join((None, Compra._meta.db_table, None, None,))
        c.query.join((Compra._meta.db_table,  # core_compra
                      CompraLineaItem._meta.db_table, # core_compralineaitem, 
                      'id', 
                      'compra_id'), 
                     promote=True)
        c.query.join((Compra._meta.db_table,
                      Proveedor._meta.db_table,
                      'proveedor_id',
                      'id',),
                     promote=True)
        c.query.join((Compra._meta.db_table,
                      Reparticion._meta.db_table,
                      'destino_id',
                      'id',),
                     promote=True)

        return c.distinct().order_by('-rank')

        


class Compra(models.Model):

    objects = CompraManager()

    orden_compra = models.IntegerField(_('Orden de Compra'), null=True, blank=True)
    fecha = models.DateField(_('Fecha'), null=True, blank=True)
    importe = models.DecimalField(_('Importe'), decimal_places=2, max_digits=19)
    suministro = models.CharField(_('Suministro'), max_length=32, null=True, blank=True)
    proveedor = models.ForeignKey(Proveedor)
    destino = models.ForeignKey(Reparticion)

    def _oc_numero(self):
        return "%s/%s" % (self.orden_compra, self.fecha.strftime("%Y"))
    oc_numero = property(_oc_numero)


    def __unicode__(self):
        return "%s compra a %s por $%s" % (self.destino, self.proveedor, self.importe)

    @models.permalink
    def get_absolute_url(self):
        return ('orden_de_compra', (),
                {'numero': self.orden_compra,
                 'anio': self.fecha.year })


class CompraLineaItem(fts_models.SearchableModel):
    compra = models.ForeignKey(Compra)
    importe_unitario = models.DecimalField(_('Importe'), decimal_places=2, max_digits=19)
    cantidad = models.CharField(_('Cantidad'), max_length=128, null=True, blank=True)
    detalle = models.TextField(_('Detalle'), null=True, blank=True)

    objects = fts_models.SearchManager(fields=('detalle',), config='spanish')

    def __unicode__(self):
        return "%s (OC: %s)" % (self.detalle, self.compra.oc_numero)
