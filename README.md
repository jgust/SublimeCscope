# SublimeCscope

A CScope plugin for Sublime Text 3. Features automatic indexing of projects and workspaces and a two level indexing strategy for large projects.

## Overview

* [Features](#features)
* [Installation](#installation)
* [Configuration](#configuration)
* [Key Bindings](#key-bindings)
* [Usage](#usage)
* [Known Issues](#known-issues)
* [License](#license)

## Features

### The usual Cscope features:
* Find symbol definitions.
* Find symbol occurrences.
* Find function callers and callees.
* Find files that include a certain h-file.
* Find an egrep pattern within the code base.
* Display the query results in the Quick Panel or in the Find Results buffer.

### Automatic indexing of projects and workspaces

Many Cscope plugins expect you to maintain your own Cscope index manually. This is cumbersome and hard to keep up to date. SublimeCscope tries to automate this as much as possible.

### Two level indexing strategy for large projects

On small projects (less than 50 files) the Cscope index is updated on-the-fly on each query. On largers projects, this is no longer feasible since updating the index becomes time consuming. Instead, the whole code base is pre-indexed and this index is kept offline and updated as needed. The files you are actively working on (i.e. open and modified files) are kept in a seperate index which is updated on-the-fly. The query result will then be a combined result of the two.

## Installation

### Package Control

TODO: This package is not published on Sublime Package Control yet.

### Manual Installation

1. Download or clone this repository to a directory `SublimeCscope` in the Sublime Text Packages directory for your platform:
    * Mac: `git clone https://github.com/jgust/SublimeCscope.git ~/Library/Application\ Support/Sublime\ Text/Packages/SublimeCscope`
    * Windows: `git clone https://github.com/jgust/SublimeCscope.git %APPDATA%\Sublime/ Text/\SublimeCscope`
    * Linux: `git clone https://github.com/jgust/SublimeCscope.git ~/.config/sublime-text-3/Packages/SublimeCscope`
2. Restart Sublime Text to complete installation. Create a project (or open an existing one) containing the files you want to index using Cscope. Make sure [Cscope][cscope] is installed on your system. If the cscope executable is not in your path you need to adjust your settings file (see [Configuration](#configuartion)).

## Configuration

SublimeCscope comes pre-configured with sane default values so no configuration should be necessary in order to get started. If you do need to modify anything such as the location of the Cscope executable or the list of file types you want to index then have a look at `Preferences->Package Settings->SublimeCscope->Settings - Default` for more details.

## Key Bindings

SublimeCscope defines no key bindings by default. Instead `Preferences->Package Settings->SublimeCscope->Key Bindings - Default` contains a template that you can use and modify at will. Just copy it to `Preferences->Package Settings->SublimeCscope->Key Bindings - User`, un-comment and modify (if needed).

## Usage

1. Open your source code project/workspace or create a new one.  SublimeCscope will detect this and automatically generate a Cscope index. For large projects you will see the current index generation progress in the left side of the status bar
2. Run any of SublimeCscope querys listed in `Tools->Packages->SublimeCscope`. SublimeCscope will use the currently selected string as a search term. If nothing is selected, SublimeCscope will try to select the word under cursor. If there is nothing under the cursor, an input dialog will be presented where you can type in the search term.
3. SublimeCscope maintains an up-to-date Cscope index as long as all changes to the code are made within Sublime Text. Any external modifications to the file tree (e.g. git pull etc) will not be detected however. In this case you may have to manually refresh the Cscope index.
Run `Project: Refresh Folders` to refresh the active project/workspace or `SublimeCscope: Refresh All Projects` to refresh all open projects.

## Known Issues

### Selecting a result in the Find Results buffer

Running any of `SublimeCscope: Find * (Use Buffer)` commands will append the results to Sublime Text's own Find Results buffer. This is mainly to be able to re-use the Jump-To-Result-On-Mouse-Click feature (which as far as I can see is impossible to implement given the current plugin API).  However, this functionality doesn't seem to work unless Sublime Text itself has actively modifed the buffer. So to work around this problem you need to keep the "Find Results" buffer open **after** performing a "Find in Folder" operation.

On the topic of the Find Results buffer, you may want to check out the [BetterFindBuffer][betterfindbuffer] plugin.


## License

SublimeCscope is released under the [MIT License][opensource].

[opensource]: http://www.opensource.org/licenses/MIT
[cscope]: http://cscope.sourceforge.net
[betterfindbuffer]: https://sublime.wbond.net/packages/BetterFindBuffer
