module.exports = function(grunt) {

  // This is where we configure each task that we'd like to run.
  grunt.initConfig({
    pkg: grunt.file.readJSON('package.json'),
    watch: {
      css: {
        files: ['*.scss'],
        tasks: ['sass', 'autoprefixer'],
        options: {
          spawn: false,
        }
      }
    },
    uglify: {
      // This is for minifying all of our scripts.
      options: {
        sourceMap: true,
        mangle: false
      },
      my_target: {
        files: [{
          expand: true,
          cwd: 'js/source',
          src: '*.js',
          dest: 'js/build'
        }]
      }
    },
    imagemin: {
      // This will optimize all of our images for the web.
      dynamic: {
        files: [{
          expand: true,
          cwd: 'images/source/',
          src: ['**/*.{png,jpg,gif}','*.{png,jpg,gif}' ],
          dest: 'images/optimized/'
        }]
      }
    },
    sass: {
      // This will compile all of our sass files
      // Additional configuration options can be found at https://github.com/gruntjs/grunt-contrib-sass
      dist: {
        options: {
          style: 'compressed', // This controls the compiled css and can be changed to nested, compact or compressed

        },
        files: [{
          expand: true,
          cwd: '',
          src: ['*.scss'],
          dest: '',
          ext: '.css'
        }]
      }
    },
    autoprefixer: {
      core: {
        options: {
          map: {
            inline: false
          }
        },
        src: '*.css'
      }
    }
  });
  // This is where we tell Grunt we plan to use this plug-in.
  grunt.loadNpmTasks('grunt-contrib-uglify');
  grunt.loadNpmTasks('grunt-contrib-imagemin');
  grunt.loadNpmTasks('grunt-contrib-sass');
  grunt.loadNpmTasks('grunt-autoprefixer');
  grunt.loadNpmTasks('grunt-contrib-watch');
  grunt.loadNpmTasks('grunt-notify');

  // Now that we've loaded the package.json and the node_modules we set the base path
  // for the actual execution of the tasks
  grunt.file.setBase('../')

  // This is where we tell Grunt what to do when we type "grunt" into the terminal.
  // Note. if you'd like to run and of the tasks individually you can do so by typing 'grunt mytaskname' alternatively
  // you can type 'grunt watch' to automatically track your files for changes.
  grunt.registerTask('default', ['watch']);
};
