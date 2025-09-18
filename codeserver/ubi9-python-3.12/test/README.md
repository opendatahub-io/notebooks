## test_codeserver_startup

Checks that the image entrypoint starts up and the image passes the readiness probe.

### Konflux considerations

Workaround for [KFLUXSPRT-5139](https://redhat-internal.slack.com/archives/C04PZ7H0VA8/p1758128206734419):

Rootless (or more like remote?) buildah, or is it shipwright on openshift, has `/dev/stderr` be a pipe that may not be reopened.
Since startup script creates some symlinks that then lead nginx to attempt to reopen `/dev/stderr`, it causes the following error:

    nginx: [alert] could not open error log file: open() "/var/log/nginx/error.log" failed (13: Permission denied)

Here's how it looks like in the Konflux container:

```
(app-root) cd /var/log/nginx/
(app-root) ls -al
total 20
drwxrwx--x. 1 default root 4096 Sep 17 17:18 .
drwxr-xr-x. 1 root    root 4096 Sep 17 15:13 ..
lrwxrwxrwx. 1 default root   11 Sep 17 17:18 access.log -> /dev/stdout
-rw-r--r--. 1 default root  132 Sep 17 17:18 codeserver.access.log
lrwxrwxrwx. 1 default root   11 Sep 17 17:18 error.log -> /dev/stderr
```

```
lrwxrwxrwx. 1 root root 15 Sep 12 11:24 /dev/stderr -> /proc/self/fd/2
l-wx------. 1 default root 64 Sep 17 17:38 /proc/self/fd/2 -> pipe:[9523152]
ls: cannot access '/dev/pts/0': No such file or directory
```

On a regular Linux machine, we have `/dev/pts/0`

```
lrwx------. 1 default root 64 Sep 17 17:34 /proc/self/fd/2 -> /dev/pts/0
```

To solve this, we need to either stop doing the symlinks for nginx, or replace /proc/self/fd/2 with something that nginx can reopen.
