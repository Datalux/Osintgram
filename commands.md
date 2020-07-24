# Commands list and usage
```
- info            Get target info
- addrs           Get all registered addressed by target photos
- followers       Get target followers
- followings      Get users followed by target
- hashtags        Get hashtags used by target
- likes           Get total likes of target's posts
- comments        Get total comments of target's posts
- tagged          Get list of users tagged by target
- photodes        Get description of target's photos
- photos          Download user's photos in output folder
- captions        Get user's photos captions
- mediatype       Get user's posts type (photo or video)
- propic          Download user's profile picture

```

### list (or help)
Show all commands avaible.

### exit
Exit from Osintgram

### FILE
Can set preference to save commands output in output folder. It save output in `<target username>_<command>.txt` file.

With `FILE=y` you can enable saving in file.

With `FILE=n` you can disable saving in file.

### JSON
Can set preference to export commands output as JSON in output folder. It save output in `<target username>_<command>.JSON` file.

With `JSON=y` you can enable JSON exporting.

With `JSON=n` you can disable JSON exporting.

### info
Show target info like:
- id
- full name
- biography
- followed
- follow
- is business account?
- business catagory (if target has business account)
- is verified?

### addrs
Return a list with address (GPS) tagged by target in his photos.
The list has post, address and date fields.

### followers
Return a list with target followers with id, nickname and full name

### followings
Return a list with users followed by target with id, nickname and full name

### hashtags
Return a list with all hashtag used by target in his photos

### likes
Return the total number of likes in target's posts

### comments
Return the total number of comments in target's posts

### photodes
Return a list with the description of the content of target's photos

### photos
Download all target's photos in output folder.
When you run the command, script ask you how many photos you want to download. 
Type ENTER to download all photos avaible or type a number to choose how many photos you want download.
```
Run a command: photos
How many photos you want to download (default all):
```

### captions 
Return a list of all captions used by target in his photos.

### mediatype
Return the number of photos and video shared by target

### propic
Download target profile picture (HD if is avaible)





