# Offline overlay of the previously verified dev2 installation.
# Before build, verify the local base ID equals:
# sha256:3b984512f460b9cb9cddac6cdb55634515b4831d1183684d7e7b557f86170131
FROM specorganon:method-superiority-dev2
USER root
COPY dist/specorganon-0.2.0rc3.dev3-py3-none-any.whl /opt/candidate/
RUN uv pip install --offline --python /opt/specorganon/venv/bin/python --no-deps --reinstall-package specorganon /opt/candidate/specorganon-0.2.0rc3.dev3-py3-none-any.whl \
    && uv pip check --python /opt/specorganon/venv/bin/python
COPY scripts/controller_native_role.py /opt/specorganon/scripts/controller_native_role.py
USER ubuntu
WORKDIR /runs
