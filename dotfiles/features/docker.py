from dotfiles.feature import Feature


class Docker(Feature):
    def apply(self, strategy):
        strategy.ensure_service("docker.service")
        strategy.ensure_group_member("docker")

    class Arch:
        def packages(self):
            return ["docker", "docker-buildx", "docker-compose"]
