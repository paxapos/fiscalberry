$(document).on("ready", function(){

    function json_remover_impresora(printerName) {
        jsonRemoverImpresora = '{"removerImpresora": "'+printerName+'"}';
        fbrry.send(jsonRemoverImpresora);
    }

	$(".panel_configuracion").on("click", function(){
		var button_string = "Abrir panel de configuración de Fiscalberry";
		$(this).val() == button_string ? al_mostrar_panel() : al_cerrar_panel();
		$("#configPanel").toggle("fade");
	});

	function al_mostrar_panel() {
	    $(".panel_configuracion").val("Cerrar panel de configuración de Fiscalberry");
	}

	function al_cerrar_panel() {
	    $(".panel_configuracion").val("Abrir panel de configuración de Fiscalberry");
	}

	$("#listadoImpresoras").on("click", ".eliminar_impresora", function(){
		var confirmacion = confirm("¿Esta seguro que desea eliminar esa impresora del config.ini?");
		if(confirmacion) {
            var nombre_impresora = $(this).parent().attr("name");
            if(nombre_impresora){
                json_remover_impresora(nombre_impresora);
                fbrry.on("fb:rta:removerImpresora", function(){
			         $(this).parent().remove();
                });
            } else {
                $(this).parent().remove();
            }
		}
	}); 

	$("#agregarImpresora").on("click", function(){
		var template = $("#nuevaImpresora").html();
		$("#listadoImpresoras").append(template);
	});

	fbrry.on("fb:rta:getActualConfig", function (ob, evt) {
        var template_for_server = $("#inputsServidor").html();
        var template_for_printer = $("#nuevaImpresora").html();
		
        for(var key in evt.data) {
        	if(key === "SERVIDOR") {
        		var puerto = evt.data[key].puerto;
        		$("#sectionServidor").append(template_for_server);
        		$("input[name='server_port']").val(puerto);
        		$("#sectionServidor").show();
        	} else {
        		var nombre_impresora = key;
        		var marca_impresora = evt.data[key].marca;
        		var driver_impresora = evt.data[key].driver;
        		var modelo_impresora = evt.data[key].modelo;
        		var host_impresora = evt.data[key].host;
        		var path_impresora = evt.data[key].path;
        		var codepage_impresora = evt.data[key].codepage;

        		$("#listadoImpresoras").append(template_for_printer);

        		var div_impresora = $("#listadoImpresoras > .impresora:last-child");
        		
        		$(div_impresora).children("input[name='nombre_impresora']").val(nombre_impresora);
                $(div_impresora).attr('name', nombre_impresora);
        		$(div_impresora).children("select[name='marca_impresora']").val(marca_impresora).trigger("change");
        		$(div_impresora).children("select[name='driver_impresora']").val(driver_impresora).trigger("change");
        		
        		if(modelo_impresora) {
        			$(div_impresora).children(".modelo_impresora").children("input[name='modelo_impresora']").val(modelo_impresora);
        		}
        		if(host_impresora) {
        			$(div_impresora).children("select[name='tipo_conexion_impresora']").val("host").trigger("change");
        			$(div_impresora).children("input[name='host_path']").val(host_impresora);
        		}
        		if(path_impresora) {
        			$(div_impresora).children("select[name='tipo_conexion_impresora']").val("path").trigger("change");
        			$(div_impresora).children("input[name='host_path']").val(path_impresora);
        		}
        		if(codepage_impresora) {
        			$(div_impresora).children(".codepage_impresora").children("input[name='codepage_impresora']").val(codepage_impresora);
        		}
        	}
        }

        $("#listadoImpresoras").show();
    });

    $("#listadoImpresoras").on("change", "select[name='marca_impresora']",function(){
    	if($(this).val() === "Hasar" || $(this).val() === "Epson") {
    		//Las fiscales no tienen codepage pero si modelo.
    		$(this).parent().children(".modelo_impresora").show();
    		$(this).parent().children(".codepage_impresora").hide();
    	} else {
    		$(this).parent().children(".modelo_impresora").hide();
    		$(this).parent().children(".codepage_impresora").show();
    	}
    });

    $("#listadoImpresoras").on("change", "select[name='tipo_conexion_impresora']",function(){
    	if($(this).val() === "path") {
    		$(this).parent().children(".nombre_tipo_conexion").text("Path: ");
    	} else {
    		$(this).parent().children(".nombre_tipo_conexion").text("Host: ");
    	}
    });

    $("#guardarConfiguracion").on("click", function(){
    	var jsonConfig = {'configure': {'puerto': '', printerName: "SERVIDOR"}};
    	var div_configPanel = $(this).parent();
    	var div_servidor = $(div_configPanel).children("#sectionServidor");
    	var div_impresoras = $(div_configPanel).children("#listadoImpresoras");

    	var puerto_servidor = $(div_servidor).children("input[name='server_port']").val();
    	jsonConfig['configure']['puerto'] = puerto_servidor;

    	//primero enviamos para actualizar la sección servidor
    	jsonConfigString = JSON.stringify(jsonConfig);
	    fbrry.send(jsonConfigString);

    	for(var key in $(div_impresoras).children(".impresora")) {
    		var printer = $(div_impresoras).children(".impresora")[key];

    		var nombre_impresora = $(printer).children("input[name='nombre_impresora']").val();
    		if(typeof nombre_impresora == "undefined") {
    			break; 
    			//despues de las impresoras, viene mucha "basura" que hace girar más el for,
    			//así que hago un break cuando ya el nombre es undefined y listo.
    		}

    		var marca_impresora = $(printer).children("select[name='marca_impresora']").val();

    		if(marca_impresora === "Hasar" || marca_impresora === "Epson") {
    			var modelo_impresora = $(printer).children(".modelo_impresora").children("input[name='modelo_impresora']").val();
    		} else {
    			var modelo_impresora = "";
    		}

    		var driver_impresora = $(printer).children("select[name='driver_impresora']").val();

    		var codepage_impresora = $(printer).children(".codepage_impresora").children("input[name='codepage_impresora']").val();

    		var tipo_conexion_impresora = $(printer).children("select[name='tipo_conexion_impresora']").val();

    		var host_path = $(printer).children("input[name='host_path']").val();

            var nombre_anterior = $(printer).attr("name");

    		jsonConfig['configure'] = {};
    		jsonConfig['configure']['marca'] = marca_impresora;
    		jsonConfig['configure']['driver'] = driver_impresora;
    		jsonConfig['configure'][tipo_conexion_impresora] = host_path;
    		jsonConfig['configure']['printerName'] = nombre_impresora;

    		if(modelo_impresora) {
    			jsonConfig['configure']['modelo'] = modelo_impresora;
    		} 
    		if(codepage_impresora) {
    			jsonConfig['configure']['codepage'] = codepage_impresora;
    		}
            if(nombre_anterior !== nombre_impresora) {
                jsonConfig['configure']['nombre_anterior'] = nombre_anterior;
            }
    		
    		//vamos enviando para guardar la configuración de cada printer por separado.
	    	jsonConfigString = JSON.stringify(jsonConfig);
	    	fbrry.send(jsonConfigString);
    	}
    });
	
});
