FROM registry.ci.openshift.org/ocp/builder:golang-1.19 AS builder

WORKDIR /go/src/github.com/openshift/openstack-sushy

COPY . .

FROM registry.ci.openshift.org/ocp/builder:rhel-9-base-openshift-4.13

RUN dnf upgrade -y \
 && dnf install -y python3-devel python3-pip \
 && dnf clean all \
 && rm -rf /var/cache/yum \
 && python3 -m pip install tox

COPY --from=builder /go/src/github.com/openshift/openstack-sushy /

