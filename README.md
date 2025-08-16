# Black-Pearl-Automatarr
Program that automates torrenting with the "ARR" suite and manages media afterwards. 

						Black Pearl Torrent Automatarr
____________________________________________________________________________________________________________________________

INTRO:

This collection of python scripts will help alleviate most of the manual intervention required when downloading, processing, and transferring files to your Plex server. Brought to you by the powers of ChatGPT, solid prompting, trial, and error.

I thought it would be fun to use pirate ship themed names for the programs that generally describe what they do.

PROGRAMS: 

captain.py
- the main program that will run as a service that run the other programs at user specified intervals. Has dry run support for testing. Has email notification support.

wash.py
- this program washes away the jumbled mess that are torrent names and renames them in Plex's format. For example this file was downloaded as: Infinity.War.2018.1080p.BluRay.REMUX.AVCDTS-HD.MA.7.1-F.mkv 
This program renamed it to: Infinity War 2018.mkv
This program single handedly saves the most amount of head aches and tedium. If you look inside the program, you will see an array of items to strip from the titles. That is largely unused now. Instead we just take the folder name that is created by Sonarr or Radarr and apply it to the movie or show. The shows can get a little tricky. We basically do the same thing as the movies but we tack on the SxxExx that is in the torrent file. This works 90% of the time. Sometimes there can be some hiccups there such as: "Its Always Sunny In Philadelphia S17E01 Web H264 Successfulcrab Eztvx To Mkv Eztvx To - S17E01". Plex can still deal with this though so its mostly only an issue if you are looking at the raw file. Has dry run support for testing.

cannon.py
- This program takes the now washed files and "shoots" them over to the Plex server. This program has saved me so much time and convenience. No more logging onto one computer and manually dragging over files from another computer to yet another computer. The Plex server's remote drive is mounted and the files are copied over. There are retries and other safety measures built in. After copying is complete the files are deleted from the torrenting computer and a success email is sent to the email of your choice. The ammount of files, the name, and the size in GB is stated. It's a nice way of keeping tabs on the progress of your downloads. The credentials for logging into the storage remote are located in the separate file "remote_credentials". Has dry run support for testing.

crows_nest.py
- This program watches qBittorrent and keeps a .json list up to date on the status of various torrents for other programs to make use of. Has email notification support.

crows_api.py
- separate program that serves the .json list. This is how the other programs will use it.

walk_plank.py
- This program will remove old torrents after a user specified ammount of time. Set to one week by default. This means that after a week of seeding we remove the files to clear up space. Additionally in the event that the torrenting computer's drives are filling up because of a massive influx of new torrents, the script will delete all seeding torrents if the disk space reaches a user set limit (default 90%). This prevents issues downloading new torrents by deprioritizing keeping old ones on disk. Has dry run support for testing.

____________________________________________________________________________________________________________________________

LOGGING:

All programs will log in their respecive log files in the captains_logs files. 

The manifest.json is also located here. 

____________________________________________________________________________________________________________________________

RECOMENDED SETTINGS:

Plex: enable auto library scans

Radarr & Sonarr: enable unmonitored deleted movies. In media management. We will not be keeping these files on the torrenting computer long term so we don't want Radarr or Sonarr to periodically download duplicates.

Have captain.py run as a service. Have captain.py and crows_api.py start up at computer start up
____________________________________________________________________________________________________________________________

LIMITATIONS/FUTURE UPDATES:

Future update will automatically search for a new torrent when one downloading stalls.

Future updates will clean up the codebase. This will include things like one place to input email credentials instead of inside each script. etc.



