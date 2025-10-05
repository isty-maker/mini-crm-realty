(function () {
  function storeInitialDisabled(control) {
    if (control.dataset.initialDisabled === undefined) {
      control.dataset.initialDisabled = control.disabled ? 'true' : 'false';
    }
  }

  function canToggle(control) {
    if (!control) {
      return false;
    }
    if (control.id === 'id_status') {
      return false;
    }
    if (control.dataset.keepEnabled === 'true') {
      return false;
    }
    if (control.hasAttribute('required')) {
      return false;
    }
    return true;
  }

  function setDisabled(section, shouldDisable) {
    var controls = section.querySelectorAll('input, select, textarea');
    controls.forEach(function (control) {
      if (!canToggle(control)) {
        return;
      }
      storeInitialDisabled(control);
      if (shouldDisable) {
        control.disabled = true;
      } else if (control.dataset.initialDisabled === 'true') {
        control.disabled = true;
      } else {
        control.removeAttribute('disabled');
      }
    });
  }

  function normalizeValue(value) {
    return (value || '').trim();
  }

  function splitValues(raw) {
    if (!raw) {
      return [];
    }
    return raw
      .split(/[\s,]+/)
      .map(function (item) {
        return normalizeValue(item);
      })
      .filter(Boolean);
  }

  function matchesOperation(tokens, currentOperation) {
    if (!tokens.length) {
      return true;
    }
    var value = normalizeValue(currentOperation);
    if (!value) {
      return false;
    }
    return tokens.some(function (token) {
      if (!token) {
        return false;
      }
      if (token === value) {
        return true;
      }
      if (token === 'rent' && value.indexOf('rent') === 0) {
        return true;
      }
      if (token === 'sale' && value === 'sale') {
        return true;
      }
      return value.indexOf(token) === 0;
    });
  }

  function sectionMatches(section, context) {
    var categories = splitValues(section.dataset.category || section.dataset.section || '');
    var operations = splitValues(section.dataset.operation || '');
    var subtypes = splitValues(section.dataset.subtype || '');

    var categoryMatch = !categories.length || categories.includes(context.category);
    if (!categoryMatch) {
      return { matches: false, disableAllowed: categories.length > 0 };
    }

    var operationMatch = matchesOperation(operations, context.operation);
    if (!operationMatch) {
      return { matches: false, disableAllowed: categories.length > 0 };
    }

    var subtypeMatch = !subtypes.length || subtypes.includes(context.subtype);
    if (!subtypeMatch) {
      return { matches: false, disableAllowed: categories.length > 0 };
    }

    return { matches: true, disableAllowed: categories.length > 0 };
  }

  function updateSections(context, sections) {
    sections.forEach(function (section) {
      var result = sectionMatches(section, context);
      if (result.matches) {
        section.hidden = false;
        setDisabled(section, false);
      } else {
        section.hidden = true;
        if (result.disableAllowed) {
          setDisabled(section, true);
        }
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

  function currentOperation() {
    var operationField = fieldByName('operation');
    return operationField ? operationField.value : '';
  }

  function currentSubtype() {
    var subtypeField = fieldByName('subtype');
    return subtypeField ? subtypeField.value : '';
  }

  function handleChange(sections) {
    updateSections(
      {
        category: normalizeValue(currentCategory()),
        operation: normalizeValue(currentOperation()),
        subtype: normalizeValue(currentSubtype())
      },
      sections
    );
  }

  document.addEventListener('DOMContentLoaded', function () {
    var categoryField = fieldByName('category');
    var subtypeField = fieldByName('subtype');
    var operationField = fieldByName('operation');
    var dataNode = document.getElementById('subtypes-data');
    var subtypeMap = {};
    var subtypePlaceholder = '— не выбрано —';
    var sections = Array.prototype.slice.call(
      document.querySelectorAll('[data-section], [data-category], [data-operation], [data-subtype]')
    );

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
        handleChange(sections);
      });
    }

    if (operationField) {
      operationField.addEventListener('change', function () {
        handleChange(sections);
      });
    }

    if (subtypeField) {
      subtypeField.addEventListener('change', function () {
        handleChange(sections);
      });
    }

    handleChange(sections);
  });
})();
