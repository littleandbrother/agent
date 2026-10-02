"""Resolve package-owned BLAS binaries, including official macOS wheel layouts."""
import hashlib
from pathlib import Path


def providers():
    import numpy
    import scipy
    from threadpoolctl import threadpool_info
    roots={}
    for owner,module in [('numpy',numpy),('scipy',scipy)]:
        package=Path(module.__file__).resolve().parent
        roots[owner]=[(package.parent/(owner+'.libs')).resolve(),
                      (package/'.libs').resolve(),(package/'.dylibs').resolve()]
    found=[];owners=set()
    for item in threadpool_info():
        if item.get('user_api')!='blas':continue
        path=Path(item['filepath']).resolve()
        owned=sorted(k for k,dirs in roots.items() if any(path.is_relative_to(r) for r in dirs))
        if not owned:continue
        row={k:v for k,v in item.items() if k!='filepath'}
        row.update(library_name=path.name,library_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),solver_packages=owned)
        found.append(row);owners.update(owned)
    if owners!={'numpy','scipy'}:
        raise RuntimeError('UNRESOLVED_NUMPY_SCIPY_BLAS_PROVIDER')
    return sorted(found,key=lambda x:(x['library_name'],x['library_sha256']))
