
ZK_VERSION := $(shell awk '/version:/ {print $$2}' snap/snapcraft.yaml | head -1 | sed "s/'//g")

.PHONY: all
all: sysdeps snap

.PHONY: snap
snap: zk_$(ZK_VERSION)_amd64.snap

zk_$(ZK_VERSION)_amd64.snap:
	SNAPCRAFT_BUILD_ENVIRONMENT_MEMORY=6G snapcraft

.PHONY: lint
lint:
	flake8 --ignore=E121,E123,E126,E226,E24,E704,E265 charm/zookeeper

.PHONY: charm
charm: charm/builds/zookeeper

charm/builds/zookeeper:
	$(MAKE) -C charm/zookeeper

.PHONY: clean
clean: clean-charm clean-snap

.PHONY: clean-charm
clean-charm:
	$(RM) -r charm/builds charm/deps
	$(RM) charm/zookeeper/*.snap

.PHONY: clean-snap
clean-snap:
	snapcraft clean

.PHONY: clean
clean: clean-snap clean-charm

sysdeps: /snap/bin/charm /snap/bin/snapcraft
/snap/bin/charm:
	sudo snap install charm --classic
/snap/bin/snapcraft:
	sudo snap install snapcraft --classic
