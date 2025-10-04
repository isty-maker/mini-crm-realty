(function () {
  function subtypeMap() {
    var container = document.getElementById('subtypes-data');
    if (!container) {
      return {};
    }
    var raw = container.getAttribute('data-subtypes') || '{}';
    try {
      return JSON.parse(raw);
    } catch (err) {
      return {};
    }
  }

  var SUBTYPE_CHOICES = subtypeMap();

  function storeInitialDisabled(control) {
    if (control.dataset.initialDisabled === undefined) {
      control.dataset.initialDisabled = control.disabled ? 'true' : 'false';
    }
  }

  function setDisabled(section, shouldDisable) {
    var controls = section.querySelectorAll('input, select, textarea');
    controls.forEach(function (control) {
      storeInitialDisabled(control);
      if (shouldDisable) {
        control.disabled = true;
      } else if (control.dataset.initialDisabled === 'true') {
        control.disabled = true;
      } else {
        control.disabled = false;
      }
    });
  }

  function normalizeType(type) {
    return (type || '').trim();
  }

  function showSection(type) {
    var target = normalizeType(type);
    var sections = document.querySelectorAll('[data-section]');
    sections.forEach(function (section) {
      var dataset = (section.dataset.section || '').split(',').map(function (value) {
        return value.trim();
      }).filter(Boolean);
      var match = target && dataset.includes(target);
      if (match) {
        section.hidden = false;
        setDisabled(section, false);
      } else {
        section.hidden = true;
        setDisabled(section, true);
      }
    });
  }

  function fieldByName(name) {
    return document.querySelector('[name="' + name + '"]') || document.getElementById('id_' + name);
  }

  function currentCategory() {
    var categoryField = fieldByName('category');
    return categoryField ? categoryField.value : '';
  }

  function rebuildSubtypeOptions(category, options) {
    var field = fieldByName('subtype');
    if (!field) {
      return;
    }

    var preserve = options && options.preserve === true;
    var previousValue = preserve ? field.value : '';
    while (field.firstChild) {
      field.removeChild(field.firstChild);
    }

    function appendOption(value, label) {
      var option = document.createElement('option');
      option.value = value;
      option.textContent = label;
      field.appendChild(option);
    }

    appendOption('', '— не выбрано —');

    var normalizedCategory = (category || '').toLowerCase();
    var choices = SUBTYPE_CHOICES[normalizedCategory] || [];
    var allowedValues = [''];
    choices.forEach(function (choice) {
      if (Array.isArray(choice) && choice.length >= 2) {
        appendOption(choice[0], choice[1]);
        allowedValues.push(String(choice[0]));
      }
    });

    if (preserve && allowedValues.indexOf(previousValue) !== -1) {
      field.value = previousValue;
    } else {
      field.value = '';
    }
  }

  function updateCategoryUi(options) {
    var category = currentCategory();
    rebuildSubtypeOptions(category, options);
    showSection(category);
  }

  document.addEventListener('DOMContentLoaded', function () {
    var categoryField = fieldByName('category');
    var subtypeField = fieldByName('subtype');
    updateCategoryUi({ preserve: true });
    if (categoryField) {
      categoryField.addEventListener('change', function () {
        updateCategoryUi({ preserve: false });
      });
    }
    if (subtypeField) {
      subtypeField.addEventListener('change', function () {
        showSection(currentCategory());
      });
    }
  });
})();
