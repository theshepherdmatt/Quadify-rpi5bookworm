#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

int main(int argc, char *argv[]) {
    if (argc != 2) {
        fprintf(stderr, "Usage: %s <remote_config_folder>\n", argv[0]);
        return 1;
    }
    // Execute the remote configuration script using bash.
    execl("/bin/bash", "bash", "/home/volumio/Quadify/scripts/install_remote_config.sh", argv[1], (char *)NULL);
    perror("execl failed");
    return 1;
}

