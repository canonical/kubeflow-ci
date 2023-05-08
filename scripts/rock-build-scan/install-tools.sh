#!/bin/bash
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Install all required tools for image definitions
#
set -e

sudo apt update
sudo apt install -y make
sudo apt install -y runc containerd
sudo apt install -y zip
sudo snap install jq
sudo snap install yq
sudo snap install go --classic
sudo snap install docker
sudo snap install --edge --devmode skopeo
sudo groupadd -f docker
sudo usermod -aG docker $USER
newgrp docker
mkdir -p /home/$USER/.docker
sudo chown "$USER":"$USER" /home/"$USER"/.docker -R
sudo chmod g+rwx "$HOME/.docker" -R
