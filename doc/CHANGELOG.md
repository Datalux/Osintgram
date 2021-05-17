# Changelog

## [1.3](https://github.com/Datalux/Osintgram/releases/tag/1.3)
**Enhancements**
- Artwork refactoring (#149) 
- Added command line mode (#155)
- Added output limiter (#201)

**Bug fixes**
- Losing collected data (#156)
- JSON user info (#202)
- Issue #198 (#200)
- Issue #204 (12e730e)


## [1.2](https://github.com/Datalux/Osintgram/releases/tag/1.2)
**Enhancements**
- Added virtual environment (#126)
- Removed some typos (#129, #118)
- Added new configuration (#125)
- Added new `commentdata` command (#131) 
- Added Docker support (#141) 


**Bug fixes**
- Fix bug  #138 (fc2a6be)
- SSL certificate error (#136) 


## [1.1](https://github.com/Datalux/Osintgram/releases/tag/1.1)
**Enhancements**
- Improved command parser (#86)
- Improved errors handling (8bd1abc)
- Add new line when input command is empty (f5211eb)
- Added new commands to catch phone number of users (#111)
- Added support for Windows (#100)


**Bug fixes**
- Fix commands output limit bug (#87)
- Fix setting target with "." in username (9082990)
- Readline installing error (#94 )


## [1.0.1](https://github.com/Datalux/Osintgram/releases/tag/1.0.1)
**Bug fixes**
- Set itself as target by param

## [1.0](https://github.com/Datalux/Osintgram/releases/tag/1.0)
**Enhancements**
- Set itself as target (#53)
-  Get others info from user (`info` command):
  - Whats'App number (if available)
  - City Name (if available)
  - Address Street (if available)
  - Contact phone number (if available)

**Bug fixes**
- Fix login issue (#79, #80, #81)

## [0.9](https://github.com/Datalux/Osintgram/releases/tag/0.9)

**Enhancements**
- Send a follow request if user not following target (#44)
- Added new `fwingsemail` command (#50)
- Added autocomplete with TAB (07e0fe8)

**Bug fixes**
- Decoding error of response [bug #46]  (f9c5f73)
- `stories` command not working (#49)

## [0.8](https://github.com/Datalux/Osintgram/releases/tag/0.8)

**Enhancements**
- Added `wtagged` command (#38)
- Added `fwersemail` command (#40)
- Access private profiles if you following targets (#37)
- Added more info in `info` command (#36)


**Bug fixes**
- Minor bug fix in `addrs` commands (9b9086a)

## [0.7](https://github.com/Datalux/Osintgram/releases/tag/0.7)

**Enhancements**
- banner now show target ID (#30) 
- persistent login (#33)
- error handler (85e390b)
- added CTRL+C handler (c2c3c3e)

**Bug fixes**
- fix likes and comments posts counter bug (44b7534)



## [0.6](https://github.com/Datalux/Osintgram/releases/tag/0.6)

**Enhancements**

- new `wcommented` command (#27)
- new `target` command
- added json dump also for captions command
- added options as arguments (#24)
- new Instagram APIs (#26)

**Bug fixes**

- fix empty addrs bug (#12)


## [0.5](https://github.com/Datalux/Osintgram/releases/tag/0.5)

**Enhancements**

- added JSON export feature

**Bug fixes**

- Fix #2

## [0.4](https://github.com/Datalux/Osintgram/releases/tag/0.4)

**Enhancements**

- added `stories` command (#8)
- added `target` command (#9)

**Bug fixes**

- added a check if the target has a private profile to avoid tool crash (#10)
- fixed `tagged` bug (#5)

## [0.3](https://github.com/Datalux/Osintgram/releases/tag/0.3)

**Enhancements**

- added `photos` command
- added `captions` command
- added `mediatype` command
- added `propic` command

## 0.2

**Enhancements**

- write in file the output of commands

## 0.1

**Initial release** 


