commit 7c554da56168c23c5bc4076c3e056a86827c1c74
Author: Asa Kirby <asakirby@gmail.com>
Date:   Thu Jan 22 09:34:30 2026 -0600

    Commit all uncommitted changes to dev branch

commit 40fe3dae2afc820fae8915670bfaa1ad038a54a6
Author: Asa Kirby <asakirby@gmail.com>
Date:   Wed Jan 21 16:49:47 2026 -0600

    feat(audio): implement smart normalization skipping with verification infrastructure
    
    Add intelligent skipping of audio transcoding when normalization is already applied:
    
    - R128 (loudnorm): Skip transcoding when file format matches target, assuming normalization is already applied
    - ReplayGain: Check for existing ReplayGain tags; skip transcoding if present
    - Force transcode option overrides smart skipping behavior
    
    Add verification infrastructure for future batch wizard:
    - SQLite-based loudness analysis cache (loudness_cache.py)
    - Verification logic and tolerance evaluation (loudness_verifier.py)
    - ReplayGain tag detection for Ogg and other containers
    
    Update process_audio() to check normalization requirements separately from codec/container mismatches, enabling selective transcode only when normalization is actually needed.
    
    Improve settings dialog resize logic to prevent scrollbars when toggling conditional fields.
    
    Update documentation and tooltips to explain smart skipping behavior and force transcode override.

commit 23455211ca1bd2296a292f1b9c6203964b5272cb
Author: Asa Kirby <asakirby@gmail.com>
Date:   Tue Jan 20 00:18:47 2026 -0600

    feat: enhance audio transcoding and settings UI
    
    - Reorganize settings dialog into a three-column layout
    - Add USDB Syncer default normalization targets for audio
    - Centralize audio transcoding logic in audio_analyzer
    - Update Opus bitrate selection to use preset values
    - Set automatic transcoding to disabled by default
    - Improve logging for media processing workflows

commit 106f0005c4d5ec8fcbc31acefed6b21fb227fac4
Author: Asa Kirby <asakirby@gmail.com>
Date:   Mon Jan 19 01:04:24 2026 -0600

    feat!: rename to Transcoder and add audio transcoding support
    
    Rename addon from "Video Transcoder" to "Transcoder" across all
    user-facing strings, documentation, and code infrastructure.
    
    Add comprehensive audio transcoding support:
    - Process standalone audio files (MP3, AAC, Vorbis, Opus)
    - Audio normalization via EBU R128 loudnorm (two-pass) and ReplayGain
    - Codec-specific quality controls (VBR quality, bitrate targets)
    - Audio batch transcoding and backup management
    - Dedicated audio settings in GUI with adaptive controls
    - Audio analyzer module mirroring video analysis patterns
    - SyncMeta updates for audio files to prevent re-download loops
    
    Update documentation with audio transcoding guide and architecture.
    
    BREAKING CHANGE: Package renamed from video_transcoder to transcoder,
    config file path changed from video_transcoder_config.json to
    transcoder_config.json. Config key force_transcode renamed to
    force_transcode_video.

commit 35d719b02f756631d2fdc3697726e7b4a8926bcc
Author: Asa Kirby <asakirby@gmail.com>
Date:   Sun Jan 11 16:20:31 2026 -0600

    fix: Remove obsolete video_transcoder workspace configuration file

commit 92536ca8923a11338053c055f3fcef8958d4280f
Author: Asa Kirby <asakirby@gmail.com>
Date:   Sun Jan 11 00:21:42 2026 -0600

    Added link to USDB Syncer

commit 45ff07afad924aac7bb11ef5fbc0dacd3c8607f1
Author: Asa Kirby <asakirby@gmail.com>
Date:   Sat Jan 10 10:02:03 2026 -0600

    fix: Correct folder path for usdb_syncer in workspace configuration

commit aa4b5fdf760f6969c5207948e14a8c75ab8f764d
Author: Asa Kirby <asakirby@gmail.com>
Date:   Sat Jan 10 09:47:13 2026 -0600

    fix: Add .DS_Store to .gitignore to prevent tracking of macOS system files

commit 32f631ef14bf39490f9372079cd68eec35ebaadb
Author: Asa Kirby <asakirby@gmail.com>
Date:   Sat Jan 10 00:53:14 2026 -0600

    fix: Correct path retrieval for video transcoder configuration file

commit 4d3dadfa6db9e26f68fb8e0acc19597ec862cddd
Author: Asa Kirby <asakirby@gmail.com>
Date:   Sat Jan 10 00:42:55 2026 -0600

    feat: Update configuration management and documentation for runtime settings storage

commit eae4cca287604d624f82598b4d26d6181f2cbfd6
Author: Asa Kirby <asakirby@gmail.com>
Date:   Fri Jan 9 23:35:43 2026 -0600

    feat: Enhance FFMPEG error handling with descriptive exit code messages

commit c76768874352889b465ad69a4591d768b7116502
Author: Asa Kirby <asakirby@gmail.com>
Date:   Fri Jan 9 23:26:36 2026 -0600

    feat: Implement rollback backup functionality with progress dialog and worker

commit c83389b2a20fe3e60531180a34ca17ae25b967db
Author: Asa Kirby <asakirby@gmail.com>
Date:   Fri Jan 9 22:37:46 2026 -0600

    docs: Acknowledge use of Kilo Code AI assistant in development and documentation

commit f8bb55cfc02744652ae17d811c504f9c7385a789
Author: Asa Kirby <asakirby@gmail.com>
Date:   Fri Jan 9 22:24:30 2026 -0600

    Delete __pycache__ directory
    
    Ignored in latest version.

commit 9b7894b86f30893543fbae06ae75b53ea6b4be74
Author: Asa Kirby <asakirby@gmail.com>
Date:   Fri Jan 9 22:20:49 2026 -0600

    feat: Update release workflow and documentation for USDB_Syncer addon compatibility

commit 173467efe92f5647cd5204e287f74a1039ac0a62
Author: Asa Kirby <asakirby@gmail.com>
Date:   Fri Jan 9 22:08:14 2026 -0600

    feat: Add GitHub Actions workflow for automated release process and documentation

commit 3f41e180b91cf293fb911f021c71d40e0fb3c1f2
Author: Asa Kirby <asakirby@gmail.com>
Date:   Fri Jan 9 21:54:07 2026 -0600

    docs: Add alternative installation instructions for .zip addons in README

commit 41f42f3023be86aa5c119cebb89f3cbbc8617b26
Author: Asa Kirby <asakirby@gmail.com>
Date:   Fri Jan 9 21:52:51 2026 -0600

    docs: Update README and ARCHITECTURE for clarity on codec support and design decisions

commit 0085b3b0c44ae6b7c9f8f69ad611ac7e31171a52
Author: Asa Kirby <asakirby@gmail.com>
Date:   Fri Jan 9 20:56:20 2026 -0600

    Refactor video transcoder rollback system
    
    - Removed the existing rollback design and implemented a new system that separates rollback functionality from user backups.
    - Rollback backups are now stored in a temporary directory, ensuring isolation from user files and automatic cleanup by the OS.
    - Introduced a backup preservation rule that maintains user backups as rolling checkpoints, always one revision behind the current video.
    - Updated `RollbackManager` to handle temporary backups and manage rollback lifecycle.
    - Enhanced `BatchTranscodeOrchestrator` to create pre-transcode backups and apply the preservation rule after successful batches.
    - Improved error handling for various scenarios, including disk space issues and rollback backup creation failures.
    - Added comprehensive testing checklist and documentation for new features and edge cases.

commit 2c6a57143930b0013c9d174911602ad3590f227d
Author: Asa Kirby <asakirby@gmail.com>
Date:   Fri Jan 9 12:36:33 2026 -0600

    docs: Add MIT license reference and AI contribution attribution

commit 202d565833584a372ebf29111903d10a130c8548
Author: Asa Kirby <asakirby@gmail.com>
Date:   Fri Jan 9 12:30:44 2026 -0600

    Add MIT license

commit 0ca7c7d6d6c24a27eb7350d566ce15cc071b1b9e
Author: Asa Kirby <asakirby@gmail.com>
Date:   Fri Jan 9 12:05:58 2026 -0600

    Update .gitignore with additional patterns

commit 29b0310674a8b3e418e31ef14a3589687aff52e4
Author: Asa Kirby <asakirby@gmail.com>
Date:   Fri Jan 9 11:56:44 2026 -0600

    Initial commit: USDB Syncer Video Transcoder Addon
