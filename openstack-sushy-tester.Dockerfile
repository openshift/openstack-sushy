FROM registry.ci.openshift.org/ocp/builder:rhel-9-base-openshift-4.13

RUN dnf upgrade -y \
 && dnf install -y python3-devel python3-pbr python3-pip \
 && dnf clean all \
 && rm -rf /var/cache/yum \
 && python3 -m pip install tox
