# SPDX-FileCopyrightText: 2025-present William Born <william.born.git@gmail.com>
#
# SPDX-License-Identifier: MIT
"""mise-en-gitlab entry point"""

import sys

if __name__ == "__main__":
    from mise_en_gitlab.cli import mise_en_gitlab

    sys.exit(mise_en_gitlab())
