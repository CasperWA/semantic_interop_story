"""Generate SOFT7 entities based on basic information:

1. Data source (DB, File, Webpage, ...)
2. Generic data source parser
3. Data source parser configuration
4. SOFT7 entity data model.

Parts 2 and 3 are together considered to produce the "specific parser" and are provided
through a single dictionary based on the `ResourceConfig` from `oteapi.models`.

"""


def __dataspace_class_factory(name, data):
    db = data
    initializer = lambda self: None
    generic_setter = (
        lambda db: lambda self, key, value: (db.document(self.id).update({key: value}))
    )(db)
    attr = dict(__init__=initializer, set_property=generic_setter)

    gen_dataspace_getset = lambda mem: lambda key: lambda: property(
        lambda self: mem[key] if key in mem else None,
        lambda self, value: (mem.update({key: value})),
    )

    gen_getset = gen_dataspace_getset(db)
    for key in data:
        attr[key] = gen_getset(key)()

    return type(name, (BaseExt,), attr)


def class_factory(name, data):
    return __dataspace_class_factory(name, data)
