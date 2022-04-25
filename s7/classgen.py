class BaseExt:
    """
    Base class
    """

    def __init__(self):
        pass


def __dataspace_class_factory(name, data):
    db = data
    initializer = lambda self: None
    generic_setter = (
        lambda db: lambda self, key, value: (db.document(self.id).update({key: value}))
    )(db)
    attr = dict(__init__=initializer, set_property=generic_setter)

    gen_dataspace_getset = lambda mem: lambda key: lambda: property(
        lambda self: mem.get(key, None),
        lambda self, value: (mem.update({key: value})),
    )

    gen_getset = gen_dataspace_getset(db)
    for key in data:
        attr[key] = gen_getset(key)()

    return type(name, (BaseExt,), attr)


def class_factory(name, data):
    return __dataspace_class_factory(name, data)
