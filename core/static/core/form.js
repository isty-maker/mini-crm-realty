(function () {
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

  function handleChange() {
    showSection(currentCategory());
  }

  document.addEventListener('DOMContentLoaded', function () {
    var categoryField = fieldByName('category');
    var subtypeField = fieldByName('subtype');
    var dataNode = document.getElementById('subtypes-data');
    var subtypeMap = {};
    var subtypePlaceholder = '— не выбрано —';

    if (dataNode) {
      if (dataNode.dataset.placeholder) {
        subtypePlaceholder = dataNode.dataset.placeholder;
      }
      try {
        subtypeMap = JSON.parse(dataNode.dataset.subtypes || '{}');
      } catch (err) {
        subtypeMap = {};
      }
    }

    function rebuildSubtypeOptions(categoryValue, keepCurrent) {
      if (!subtypeField) {
        return;
      }

      var currentValue = keepCurrent ? subtypeField.value : '';
      while (subtypeField.options.length > 0) {
        subtypeField.remove(0);
      }

      var placeholderOption = document.createElement('option');
      placeholderOption.value = '';
      placeholderOption.textContent = subtypePlaceholder;
      subtypeField.appendChild(placeholderOption);

      var options = subtypeMap[categoryValue] || [];
      options.forEach(function (pair) {
        var option = document.createElement('option');
        option.value = pair[0];
        option.textContent = pair[1];
        subtypeField.appendChild(option);
      });

      if (keepCurrent && currentValue) {
        var isAllowed = options.some(function (pair) {
          return pair[0] === currentValue;
        });
        if (isAllowed) {
          subtypeField.value = currentValue;
          return;
        }
      }

      subtypeField.value = '';
    }

    if (dataNode && categoryField && subtypeField) {
      rebuildSubtypeOptions(categoryField.value, true);
    }

    if (categoryField) {
      categoryField.addEventListener('change', function () {
        if (dataNode && subtypeField) {
          rebuildSubtypeOptions(categoryField.value, false);
        }
        handleChange();
      });
    }

    if (subtypeField) {
      subtypeField.addEventListener('change', handleChange);
    }

    handleChange();
  });
})();
