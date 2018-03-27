# deploy-openshift

This builds a docker container that knows how to deploy a simple
OpenShift deployment on three nodes. This configuration is not production ready but
can serve as a simple test bed


```
[user@host]$ docker build -t deploy-openshift .

[user@host]$ docker run -it --rm deploy-openshift
usage: deploy-scaleio.py [-h] [--ip [IP [IP ...]]]
                         [--username USERNAME]
                         [--password PASSWORD]
                         --version <version>
```
