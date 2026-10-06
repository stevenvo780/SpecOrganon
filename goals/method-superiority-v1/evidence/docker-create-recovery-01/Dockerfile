# Overlay of the inspected immutable local base 6d196a4a021b872e2ea7d799e1797834e23b570e635bd640095f4521cca04ce2.
FROM specorganon:method-superiority-dev4
USER root
COPY releases/method-superiority/dev5/specorganon-0.2.0rc3.dev5-py3-none-any.whl /opt/candidate/
RUN uv pip install --offline --python /opt/specorganon/venv/bin/python --no-deps --reinstall-package specorganon /opt/candidate/specorganon-0.2.0rc3.dev5-py3-none-any.whl \
    && uv pip check --python /opt/specorganon/venv/bin/python
USER ubuntu
WORKDIR /runs
