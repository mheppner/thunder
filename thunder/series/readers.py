from numpy import array, arange, frombuffer, load, asarray, random, \
    fromstring, expand_dims, unravel_index

from ..utils import check_spark
spark = check_spark()


def fromrdd(rdd, nrecords=None, shape=None, index=None, dtype=None):
    """
    Load Series object from a Spark RDD.

    Assumes keys are tuples with increasing and unique indices,
    and values are 1d ndarrays. Will try to infer properties
    that are not explicitly provided.

    Parameters
    ----------
    rdd : SparkRDD
        An RDD containing series data.

    shape : tuple or array, optional, default = None
        Total shape of data (if provided will avoid check).

    nrecords : int, optional, default = None
        Number of records (if provided will avoid check).

    index : array, optional, default = None
        Index for records, if not provided will use (0, 1, ...)

    dtype : string, default = None
       Data numerical type (if provided will avoid check)
    """
    from .series import Series
    from bolt.spark.array import BoltArraySpark

    if index is None or dtype is None:
        item = rdd.values().first()

    if index is None:
        index = range(len(item))

    if dtype is None:
        dtype = item.dtype

    if shape is None or nrecords is None:
        nrecords = rdd.count()

    if shape is None:
        shape = (nrecords, asarray(index).shape[0])

    values = BoltArraySpark(rdd, shape=shape, dtype=dtype, split=len(shape)-1)
    return Series(values, index=index)

def fromarray(values, index=None, npartitions=None, engine=None):
    """
    Load Series object from a local numpy array.

    Assumes that all but final dimension index the records,
    and the size of the final dimension is the length of each record,
    e.g. a (2, 3, 4) array will be treated as 2 x 3 records of size (4,)

    Parameters
    ----------
    values : array-like
        An array containing the data.

    index : array, optional, default = None
        Index for records, if not provided will use (0,1,...,N)
        where N is the length of each record.

    npartitions : int, default = None
        Number of partitions for parallelization (Spark only)

    engine : object, default = None
        Computational engine (e.g. a SparkContext for Spark)
    """
    from .series import Series
    import bolt

    values = asarray(values)

    if values.ndim < 2:
        values = expand_dims(values, 0)

    if index is not None and not asarray(index).shape[0] == values.shape[-1]:
        raise ValueError('Index length %s not equal to record length %s'
                         % (asarray(index).shape[0], values.shape[-1]))
    if index is None:
        index = arange(values.shape[-1])

    if spark and isinstance(engine, spark):
        axis = tuple(range(values.ndim - 1))
        values = bolt.array(values, context=engine, npartitions=npartitions, axis=axis)
        return Series(values, index=index)

    return Series(values, index=index)

def fromlist(items, accessor=None, index=None, dtype=None, npartitions=None, engine=None):
    """
    Create a Series object from a list of items and optional accessor function.

    Will call accessor function on each item from the list,
    providing a generic interface for data loading.

    Parameters
    ----------
    items : list
        A list of items to load.

    accessor : function, optional, default = None
        A function to apply to each item in the list during loading.

    index : array, optional, default = None
        Index for records, if not provided will use (0,1,...,N)
        where N is the length of each record.

    dtype : string, default = None
       Data numerical type (if provided will avoid check)

    npartitions : int, default = None
        Number of partitions for parallelization (Spark only)

    engine : object, default = None
        Computational engine (e.g. a SparkContext for Spark)
    """
    if spark and isinstance(engine, spark):
        if dtype is None:
            dtype = accessor(items[0]).dtype if accessor else items[0].dtype
        nrecords = len(items)
        keys = map(lambda k: (k, ), range(len(items)))
        if not npartitions:
            npartitions = engine.defaultParallelism
        items = zip(keys, items)
        rdd = engine.parallelize(items, npartitions)
        if accessor:
            rdd = rdd.mapValues(accessor)
        return fromrdd(rdd, nrecords=nrecords, index=index, dtype=dtype)

    else:
        if accessor:
            items = [accessor(i) for i in items]
        return fromarray(items, index=index)

def frommat(path, var, index=None, npartitions=None, engine=None):
    """
    Loads Series data stored in a Matlab .mat file.

    Parameters
    ----------
    path : str
        Path to data file.

    var : str
        Variable name.

    index : array, optional, default = None
        Index for records, if not provided will use (0,1,...,N)
        where N is the length of each record.

    npartitions : int, default = None
        Number of partitions for parallelization (Spark only)

    engine : object, default = None
        Computational engine (e.g. a SparkContext for Spark)
    """
    from scipy.io import loadmat
    data = loadmat(path)[var]
    if data.ndim > 2:
        raise IOError('Input data must be one or two dimensional')

    return fromarray(data, npartitions=npartitions, index=index, engine=engine)

def fromnpy(path,  index=None, npartitions=None, engine=None):
    """
    Loads Series data stored in the numpy save() .npy format.

    Parameters
    ----------
    path : str
        Path to data file.

    index : array, optional, default = None
        Index for records, if not provided will use (0,1,...,N)
        where N is the length of each record.

    npartitions : int, default = None
        Number of partitions for parallelization (Spark only)

    engine : object, default = None
        Computational engine (e.g. a SparkContext for Spark)
    """
    data = load(path)
    if data.ndim > 2:
        raise IOError('Input data must be one or two dimensional')

    return fromarray(data, npartitions=npartitions, index=index, engine=engine)

def fromtext(path, ext='txt', dtype='float64', skip=0, shape=None, index=None,
             engine=None, npartitions=None, credentials=None):
    """
    Loads Series data from text files.

    Assumes data are formatted as rows, where each record is a row
    of numbers separated by spaces e.g. 'v v v v v'. You can
    optionally specify a fixed number of initial items per row to skip / discard.

    Parameters
    ----------
    path : string
        Directory to load from, can be a URI string with scheme
        (e.g. "file://", "s3n://", or "gs://"), or a single file,
        or a directory, or a directory with a single wildcard character.

    ext : str, optional, default = 'txt'
        File extension.

    dtype: dtype or dtype specifier, default 'float64'
        Numerical type to use for data after converting from text.

    skip : int, optional, default = 0
        Number of items in each record to skip.

    shape : tuple or list, optional, default = None
        Shape of data if known, will be inferred otherwise.

    index : array, optional, default = None
        Index for records, if not provided will use (0, 1, ...)

    engine : object, default = None
        Computational engine (e.g. a SparkContext for Spark)

    npartitions : int, default = None
        Number of partitions for parallelization (Spark only)

    credentials : dict, default = None
        Credentials for remote storage (e.g. S3) in the form {access: ***, secret: ***}
    """
    from thunder.readers import normalize_scheme, get_parallel_reader
    path = normalize_scheme(path, ext)

    if spark and isinstance(engine, spark):

        def parse(line, skip):
            vec = [float(x) for x in line.split(' ')]
            return array(vec[skip:], dtype=dtype)

        lines = engine.textFile(path, npartitions)
        data = lines.map(lambda x: parse(x, skip))
        rdd = data.zipWithIndex().map(lambda (ary, idx): ((idx,), ary))
        return fromrdd(rdd, dtype=str(dtype), shape=shape, index=index)

    else:
        reader = get_parallel_reader(path)(engine, credentials=credentials)
        data = reader.read(path, ext=ext)

        values = []
        for kv in data:
            for line in kv[1].split('\n')[:-1]:
                values.append(fromstring(line, sep=' '))
        values = asarray(values)

        if skip > 0:
            values = values[:, skip:]

        if shape:
            values = values.reshape(shape)

        return fromarray(values, index=index)

def frombinary(path, ext='bin', conf='conf.json', dtype=None, shape=None, skip=0,
               index=None, engine=None, credentials=None):
    """
    Load a Series object from flat binary files.

    Parameters
    ----------
    path : string URI or local filesystem path
        Directory to load from, can be a URI string with scheme
        (e.g. "file://", "s3n://", or "gs://"), or a single file,
        or a directory, or a directory with a single wildcard character.

    ext : str, optional, default = 'bin'
        Optional file extension specifier.

    conf : str, optional, default = 'conf.json'
        Name of conf file with type and size information.

    dtype: dtype or dtype specifier, default 'float64'
        Numerical type to use for data after converting from text.

    shape : tuple or list, optional, default = None
        Shape of data if known, will be inferred otherwise.

    skip : int, optional, default = 0
        Number of items in each record to skip.

    index : array, optional, default = None
        Index for records, if not provided will use (0, 1, ...)

    engine : object, default = None
        Computational engine (e.g. a SparkContext for Spark)

    credentials : dict, default = None
        Credentials for remote storage (e.g. S3) in the form {access: ***, secret: ***}
    """
    shape, dtype = binaryconfig(path, conf, dtype, shape, credentials)

    from thunder.readers import normalize_scheme, get_parallel_reader
    path = normalize_scheme(path, ext)

    from numpy import dtype as dtype_func
    recordsize = dtype_func(dtype).itemsize * (shape[-1] + skip)

    if spark and isinstance(engine, spark):
        lines = engine.binaryRecords(path, recordsize)
        raw = lines.map(lambda x: frombuffer(buffer(x, 0, recordsize), dtype=dtype)[skip:])
        rdd = raw.zipWithIndex().map(lambda (ary, idx): ((idx,), ary))

        if shape and len(shape) > 2:
            expand = lambda k: unravel_index(k[0], shape[0:-1])
            rdd = rdd.map(lambda (k, v): (expand(k), v))

        if not index:
            index = arange(shape[-1])

        return fromrdd(rdd, dtype=dtype, shape=shape, index=index)

    else:
        reader = get_parallel_reader(path)(engine, credentials=credentials)
        data = reader.read(path, ext=ext)

        values = []
        for record in data:
            buf = record[1]
            offset = 0
            while offset < len(buf):
                v = frombuffer(buffer(buf, offset, recordsize), dtype=dtype)
                values.append(v[skip:])
                offset += recordsize

        values = asarray(values, dtype=dtype)

        if shape:
            values = values.reshape(shape)

        return fromarray(values, index=index)

def binaryconfig(path, conf, dtype=None, shape=None, credentials=None):
    """
    Collects parameters to use for binary series loading.
    """
    import json
    from thunder.readers import get_file_reader, FileNotFoundError

    reader = get_file_reader(path)(credentials=credentials)
    try:
        buf = reader.read(path, filename=conf)
        params = json.loads(buf)
    except FileNotFoundError:
        params = {}

    if dtype:
        params['dtype'] = dtype

    if shape:
        params['shape'] = shape

    if 'dtype' not in params.keys():
        raise ValueError('dtype not specified either in conf.json or as argument')

    if 'shape' not in params.keys():
        raise ValueError('shape not specified either in conf.json or as argument')

    return params['shape'], params['dtype']

def fromrandom(shape=(100, 10), npartitions=1, seed=42, engine=None):
    """
    Generate gaussian random series data.

    Parameters
    ----------
    shape : tuple
        Dimensions of data.

    npartitions : int
        Number of partitions with which to distribute data.

    seed : int
        Randomization seed.
    """
    seed = hash(seed)

    def generate(v):
        random.seed(seed + v)
        return random.randn(shape[1])

    return fromlist(range(shape[0]), accessor=generate, npartitions=npartitions, engine=engine)

def fromexample(name=None, engine=None):
    """
    Load example series data.

    Data must be downloaded from S3, so this method requires
    an internet connection.

    Parameters
    ----------
    name : str
        Name of dataset, options include 'iris' | 'mouse' | 'fish'.
        If not specified will print options.
    """
    import os
    import tempfile
    import shutil
    import checkist
    from boto.s3.connection import S3Connection

    datasets = ['iris', 'mouse', 'fish']

    if name is None:
        print 'Availiable example series datasets'
        for d in datasets:
            print '- ' + d
        return

    checkist.opts(name, datasets)

    d = tempfile.mkdtemp()

    try:
        os.mkdir(os.path.join(d, 'series'))
        os.mkdir(os.path.join(d, 'series', name))
        conn = S3Connection(anon=True)
        bucket = conn.get_bucket('thunder-sample-data')
        for key in bucket.list(os.path.join('series', name)):
            if not key.name.endswith('/'):
                key.get_contents_to_filename(os.path.join(d, key.name))
        data = frombinary(os.path.join(d, 'series', name), engine=engine)

        if spark and isinstance(engine, spark):
            data.cache()
            data.compute()

    finally:
        shutil.rmtree(d)

    return data