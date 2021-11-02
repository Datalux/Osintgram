# Commands list and usage
```
- addrs           Get all registered addressed by target photos
- captions        Get user's photos captions
- commentdata     Get a list of all the comments on the target's posts
- comments        Get total comments of target's posts
- followers       Get target followers
- followings      Get users followed by target
- fwersemail      Get email of target followers
- fwingsemail     Get email of users followed by target
- hashtags        Get hashtags used by target
- info            Get target info
- likes           Get total likes of target's posts
- mediatype       Get user's posts type (photo or video)
- photodes        Get description of target's photos
- photos          Download user's photos in output folder
- propic          Download user's profile picture
- stories         Download user's stories  
- tagged          Get list of users tagged by target
- wcommented      Get a list of user who commented target's photos
- wtagged         Get a list of user who tagged target
```

### addrs
Return a list with address (GPS) tagged by target in his photos.
The list has post, address and date fields.

### captions 
Return a list of all captions used by target in his photos.

### commentdata
Return a list of all the comments on the target's posts

### comments
Return the total number of comments in target's posts

### exit
Exit from Osintgram

### FILE
Can set preference to save commands output in output folder. It save output in `<target username>_<command>.txt` file.

With `FILE=y` you can enable saving in file.

With `FILE=n` you can disable saving in file.

### followers
Return a list with target followers with id, nickname and full name

### followings
Return a list with users followed by target with id, nickname and full name

### fwersemail
Return a list of emails of target followers

### fwingsemail
Return a list of emails of user followed by target

### fwersnumber
Return a list of phone number of target followers

### fwingsnumber
Return a list of phone number of user followed by target

### hashtags
Return a list with all hashtag used by target in his photos

### info
Show target info like:
- id
- full name
- biography
- followed
- follow
- is business account?
- business category (if target has business account)
- is verified?
- business email (if available)
- HD profile picture url
- connected Facebook page (if available)
- Whats'App number (if available)
- City Name (if available)
- Address Street (if available)
- Contact phone number (if available)

### JSON
Can set preference to export commands output as JSON in output folder. It save output in `<target username>_<command>.JSON` file.

With `JSON=y` you can enable JSON exporting.

With `JSON=n` you can disable JSON exporting.

### likes
Return the total number of likes in target's posts

### list (or help)
Show all commands available.

### mediatype
Return the number of photos and video shared by target

### photodes
Return a list with the description of the content of target's photos

### photos
Download all target's photos in output folder.
When you run the command, script ask you how many photos you want to download. 
Type ENTER to download all photos available or type a number to choose how many photos you want download.
```
Run a command: photos
How many photos you want to download (default all):
```

### propic
Download target profile picture (HD if is available)

### stories
Download all target's stories in output folder.

## tagged
Return a list of users tagged by target with ID, username and full name

## wcommented
Return a list of users who commented target's photos sorted by number of comments

## wtagged
Return a list of users who tagged target sorted by number of photos


