# ckanext-cioos_theme

This is the CIOOS-SIOOC Theme extension. It is primarily focused on customizing
the look and feel of the ckan site to match the main CIOOS site. As well as
stylistic changes this extension also adds some functionality in new page
layouts as well as search support in the form of new facits.

Current modifications include:
* scheming validator to clean up and populate the EOV field from harvested tags and keyword fields. This is done by matching keyword and tag entries to the defined choose list for the EOV field and including any words that match. keywords are currently not removed from their original locations so some duplicat entrie will accure.
* Add logging to put loging and connection attempts to the docker logs. This is to support fail2ban scraping of logs in an attempt to prevent the most basic of brute force attacks
* Add EOV facet to support searching for datasets by EOV.
* Copies keyword field into tags_en and tags_fr for easier indexing and searching by langauge
* many small tweeks to page layout mostly to the dataset and home page.


------------
Requirements
------------
Tested on ckan 2.8 but likely works for earlyer versions. This extension requires ckanext-scheming, ckanext-composite, and chanext-fluent to also be installed. If these extensions are missing this code will do very little.

------------
Installation
------------

.. Add any additional install steps to the list below.
   For example installing any non-Python dependencies or adding any required
   config settings.

To install ckanext-cioos_theme:

1. Activate your CKAN virtual environment, for example::

     . /usr/lib/ckan/default/bin/activate

2. Install the ckanext-cioos_theme Python package into your virtual environment::

     pip install ckanext-cioos_theme

3. Add ``sep`` to the ``ckan.plugins`` setting in your CKAN
   config file (by default the config file is located at
   ``/etc/ckan/default/production.ini``).

4. Restart CKAN. For example if you've deployed CKAN with Apache on Ubuntu::

     sudo service apache2 reload


-----------------
Running the Tests
-----------------

Sorry, no test at this time
