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

  var SCROLL_STORAGE_KEY = 'panel:scroll';

  function getCsrfToken() {
    var input = document.querySelector('input[name="csrfmiddlewaretoken"]');
    if (input && input.value) {
      return input.value;
    }
    var match = document.cookie ? document.cookie.match(/csrftoken=([^;]+)/) : null;
    return match ? decodeURIComponent(match[1]) : null;
  }

  function saveScrollPosition() {
    try {
      var photos = document.getElementById('photos');
      var top = window.scrollY || window.pageYOffset || 0;
      var payload = {
        scrollY: top,
        photosTop: photos
          ? photos.getBoundingClientRect().top + top
          : null
      };
      sessionStorage.setItem(SCROLL_STORAGE_KEY, JSON.stringify(payload));
    } catch (err) {
      /* no-op */
    }
  }

  function restoreScrollPosition() {
    try {
      var raw = sessionStorage.getItem(SCROLL_STORAGE_KEY);
      if (!raw) {
        return;
      }
      sessionStorage.removeItem(SCROLL_STORAGE_KEY);
      var payload = JSON.parse(raw);
      if (payload && typeof payload.scrollY === 'number') {
        window.scrollTo(0, payload.scrollY);
        return;
      }
      if (payload && typeof payload.photosTop === 'number') {
        window.scrollTo(0, payload.photosTop);
      }
    } catch (err) {
      try {
        sessionStorage.removeItem(SCROLL_STORAGE_KEY);
      } catch (e) {
        /* ignore */
      }
    }
  }

  function attachScrollPersistence() {
    var forms = document.querySelectorAll('form[data-preserve-scroll="true"]');
    forms.forEach(function (form) {
      form.addEventListener('submit', function () {
        saveScrollPosition();
      });
    });
  }

  function setupPhotoActions() {
    var list = document.getElementById('photos');
    if (!list) {
      attachScrollPersistence();
      return;
    }

    var bulkBar = document.querySelector('.photo-bulk-actions');
    var selectAllBtn = document.getElementById('photo-select-all');
    var clearSelectionBtn = document.getElementById('photo-clear-selection');
    var deleteSelectedBtn = document.getElementById('photo-delete-selected');
    var deleteAllBtn = document.getElementById('photo-delete-all');
    var selectionInfo = document.getElementById('photo-selection-info');
    var reorderForm = document.getElementById('reorderForm');

    function cards() {
      return Array.prototype.slice.call(list.querySelectorAll('.photo-item'));
    }

    function toggleCardHighlight(checkbox, selected) {
      var card = checkbox ? checkbox.closest('.photo-item') : null;
      if (card) {
        if (selected) {
          card.classList.add('selected');
        } else {
          card.classList.remove('selected');
        }
      }
    }

    function updateSelectionInfo() {
      var checked = list.querySelectorAll('.photo-select:checked');
      var count = checked.length;
      if (selectionInfo) {
        selectionInfo.textContent = count ? 'Выбрано: ' + count : '';
      }
      if (deleteSelectedBtn) {
        deleteSelectedBtn.disabled = count === 0;
      }
      if (clearSelectionBtn) {
        clearSelectionBtn.disabled = count === 0;
      }
    }

    function setSelectionForAll(checked) {
      var boxes = list.querySelectorAll('.photo-select');
      boxes.forEach(function (box) {
        box.checked = checked;
        toggleCardHighlight(box, checked);
      });
      updateSelectionInfo();
    }

    function removeCardsByIds(ids) {
      ids.forEach(function (id) {
        var card = list.querySelector('.photo-item[data-photo-id="' + id + '"]');
        if (card) {
          card.remove();
        }
      });
    }

    function ensureEmptyState() {
      if (cards().length > 0) {
        return;
      }
      if (bulkBar) {
        bulkBar.style.display = 'none';
      }
      if (reorderForm) {
        reorderForm.style.display = 'none';
      }
      var emptyText = list.dataset.emptyText || '';
      if (emptyText) {
        list.innerHTML = '<p>' + emptyText + '</p>';
      } else {
        list.innerHTML = '';
      }
    }

    function postDelete(ids) {
      if (!bulkBar) {
        return Promise.resolve([]);
      }
      var url = bulkBar.dataset.bulkDeleteUrl;
      var propertyId = bulkBar.dataset.propertyId;
      if (!url || !propertyId) {
        return Promise.resolve([]);
      }
      var params = new URLSearchParams();
      params.append('property_id', propertyId);
      ids.forEach(function (id) {
        params.append('ids[]', id);
      });
      var headers = { 'X-Requested-With': 'XMLHttpRequest' };
      var token = getCsrfToken();
      if (token) {
        headers['X-CSRFToken'] = token;
      }
      return fetch(url, {
        method: 'POST',
        headers: headers,
        body: params
      }).then(
        function (response) {
          if (!response.ok) {
            return response
              .json()
              .catch(function () {
                return {};
              })
              .then(function (payload) {
                var error = payload && payload.error ? payload.error : 'unknown';
                throw new Error(error);
              });
          }
          return response.json();
        }
      );
    }

    function handleDelete(ids, confirmMessage) {
      if (!ids.length) {
        return;
      }
      if (confirmMessage && !window.confirm(confirmMessage)) {
        return;
      }
      var buttonToDisable = ids.length === cards().length ? deleteAllBtn : deleteSelectedBtn;
      if (buttonToDisable) {
        buttonToDisable.disabled = true;
      }
      var enableButtons = function () {
        if (buttonToDisable) {
          buttonToDisable.disabled = false;
        }
      };
      postDelete(ids)
        .then(function (payload) {
          var removed = (payload && payload.deleted) || [];
          removeCardsByIds(removed);
          updateSelectionInfo();
          ensureEmptyState();
        })
        .catch(function () {
          window.alert('Не удалось удалить фото. Попробуйте ещё раз.');
        })
        .then(enableButtons, enableButtons);
    }

    list.addEventListener('change', function (event) {
      var target = event.target;
      if (target && target.classList && target.classList.contains('photo-select')) {
        toggleCardHighlight(target, target.checked);
        updateSelectionInfo();
      }
    });

    if (selectAllBtn) {
      selectAllBtn.addEventListener('click', function () {
        setSelectionForAll(true);
      });
    }

    if (clearSelectionBtn) {
      clearSelectionBtn.addEventListener('click', function () {
        setSelectionForAll(false);
      });
    }

    if (deleteSelectedBtn) {
      deleteSelectedBtn.addEventListener('click', function () {
        var ids = Array.prototype.slice
          .call(list.querySelectorAll('.photo-select:checked'))
          .map(function (box) {
            return box.value;
          });
        handleDelete(ids, 'Удалить выбранные фото?');
      });
    }

    if (deleteAllBtn) {
      deleteAllBtn.addEventListener('click', function () {
        var ids = cards().map(function (card) {
          return card.dataset.photoId;
        });
        handleDelete(ids, 'Удалить все фото?');
      });
    }

    updateSelectionInfo();
    attachScrollPersistence();
  }

  document.addEventListener('DOMContentLoaded', function () {
    restoreScrollPosition();
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
    setupPhotoActions();
  });
})();
