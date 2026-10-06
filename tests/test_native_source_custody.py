"""Native source identity fixtures; never tools or provider invocations."""
from pathlib import Path

import pytest

from specorganon.docker_roles import DockerRoles,DockerRoleError
from specorganon.role_jobs import _json,_write


def transport(tmp_path,monkeypatch):
    source=tmp_path/'source';(source/'scripts').mkdir(parents=True)
    (source/'src/specorganon').mkdir(parents=True)
    (source/'scripts/controller_native_role.py').write_text('# bridge fixture')
    (source/'src/specorganon/__init__.py').write_text('# library fixture')
    catalog=tmp_path/'catalog.json';catalog.write_text('{"models":[]}')
    profile=tmp_path/'profile';profile.mkdir();exe=tmp_path/'agy';exe.write_text('fixture only')
    monkeypatch.setattr(DockerRoles,'_image',staticmethod(lambda ref:ref))
    options={'source_root':source,'native_image':'sha256:'+'a'*64,'test_image':'sha256:'+'b'*64,
             'public_catalog':catalog,'gemini_profile':profile,'gemini_executable':exe}
    root=tmp_path/'transport';return DockerRoles(root,**options),source,options


@pytest.mark.parametrize('change',['bridge','module','added_module'])
def test_source_change_cannot_resume_transport_or_prepare_next_native_job(tmp_path,monkeypatch,change):
    t,s,options=transport(tmp_path,monkeypatch)
    p=s/({'bridge':'scripts/controller_native_role.py','module':'src/specorganon/__init__.py',
          'added_module':'src/specorganon/new.py'}[change]);p.write_text('# changed fixture')
    with pytest.raises(DockerRoleError,match='native source changed'):
        t._prepare('new-job','review',{'fixture':True})
    assert not (t.root/'jobs/new-job').exists()
    with pytest.raises(DockerRoleError,match='policy changed'):DockerRoles(t.root,**options)


def test_prior_schema3_cannot_silently_add_source_binding(tmp_path,monkeypatch):
    t,s,options=transport(tmp_path,monkeypatch);p=_json(t.root/'transport-policy.json')
    p['schema']=3;p.pop('native_source_sha256');_write(t.root/'transport-policy.json',p)
    with pytest.raises(DockerRoleError,match='schema5'):DockerRoles(t.root,**options)


def test_native_input_uses_exact_checked_bytes_not_second_copy_reads(tmp_path,monkeypatch):
    t,s,options=transport(tmp_path,monkeypatch)
    expected=t._bound_native_source_bytes(); original=t._bound_native_source_bytes
    def capture_then_change():
        raw=original();(s/'scripts/controller_native_role.py').write_text('# change after checked read')
        return raw
    monkeypatch.setattr(t,'_bound_native_source_bytes',capture_then_change)
    folder,plan=t._prepare('snapshot-job','review',{'fixture':True})
    assert (folder/'input/bridge.py').read_bytes()==expected['scripts/controller_native_role.py']
    assert (folder/'input/library/specorganon/__init__.py').read_bytes()==expected['src/specorganon/__init__.py']
    assert plan['container_id'] is None


def registered_transport(tmp_path,monkeypatch):
    from specorganon.role_jobs import _read,digest
    _,source,options=transport(tmp_path,monkeypatch)
    catalog=source/'catalog.json';catalog.write_text('{"models":[]}')
    seccomp=source/'seccomp.json';seccomp.write_text('{"defaultAction":"SCMP_ACT_ERRNO"}')
    bindings={str(p.relative_to(source)):digest(_read(p)) for p in source.rglob('*') if p.is_file()}
    options.update(public_catalog=catalog,seccomp=seccomp,source_bindings=bindings)
    t=DockerRoles(tmp_path/'registered-transport',**options)
    return t,source,options


@pytest.mark.parametrize('name',['catalog.json','seccomp.json'])
def test_registered_launch_input_drift_rejected_before_job_creation(tmp_path,monkeypatch,name):
    t,s,options=registered_transport(tmp_path,monkeypatch)
    (s/name).write_text('{"changed":true}')
    with pytest.raises(DockerRoleError,match='launch input changed'):t._prepare('new','author',{'fixture':True})
    assert not (t.root/'jobs/new').exists()
    with pytest.raises(DockerRoleError,match='registered source binding'):
        DockerRoles(tmp_path/'another',**options)


@pytest.mark.parametrize('name',['catalog.json','seccomp.json'])
def test_launch_uses_same_checked_bytes_in_private_snapshot(tmp_path,monkeypatch,name):
    import specorganon.docker_roles as dr
    t,s,_=registered_transport(tmp_path,monkeypatch)
    original=dr._read;expected=original(s/name)
    def capture_then_change(path,*args,**kwargs):
        raw=original(path,*args,**kwargs)
        if Path(path)==s/name:(s/name).write_text('{"changed_after_read":true}')
        return raw
    monkeypatch.setattr(dr,'_read',capture_then_change)
    folder,plan=t._prepare('snapshot','author',{'fixture':True})
    dest='public-models.json' if name=='catalog.json' else 'seccomp.json'
    assert (folder/'input'/dest).read_bytes()==expected
    assert 'seccomp='+str(folder/'input/seccomp.json') in plan['create_argv']
    assert 'seccomp='+str(s/'seccomp.json') not in plan['create_argv']
    assert plan['input_manifest'][dest]==dr.digest(expected)


def test_registered_code_binding_required_at_transport_construction(tmp_path,monkeypatch):
    t,s,options=registered_transport(tmp_path,monkeypatch)
    del options['source_bindings']['scripts/controller_native_role.py']
    with pytest.raises(DockerRoleError,match='registered source binding'):
        DockerRoles(tmp_path/'unbound',**options)
