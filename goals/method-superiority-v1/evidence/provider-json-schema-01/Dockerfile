# Offline overlay. Verified local base ID: sha256:5367d61b07966388a174632fef1418edd491eff55730def6bdf917ae802e67f8
FROM specorganon:method-superiority-dev3
USER root
COPY dist/specorganon-0.2.0rc3.dev4-py3-none-any.whl /opt/candidate/
RUN uv pip install --offline --python /opt/specorganon/venv/bin/python --no-deps --reinstall-package specorganon /opt/candidate/specorganon-0.2.0rc3.dev4-py3-none-any.whl \
    && uv pip check --python /opt/specorganon/venv/bin/python
COPY scripts/controller_native_role.py /opt/specorganon/scripts/controller_native_role.py
USER ubuntu
WORKDIR /runs
