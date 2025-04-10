# Model Context Document (MDC)

## Descripción del Sistema

### Propósito Principal
- Sistema de monitoreo aéreo
- Detección de vuelos interesantes usando API de aeronáutica
- Creación automática de mensajes
- Distribución en redes sociales

## Tecnologías Principales

### Lenguaje
- **Python 3.x**: Lenguaje principal del proyecto

### API de Aeronáutica
- Consulta de datos de vuelos en tiempo real
- Filtrado de vuelos interesantes
- Integración con múltiples fuentes de datos

### Frameworks
- **Telegram Bot Framework**: Para integración con Telegram
- **Twikit**: Biblioteca oficial para interactuar con Twitter

### APIs Externas
- **Twitter**: Mediante Twikit
- **Instagram**: Integración directa
- **LinkedIn**: Integración directa

### Implementaciones Custom
- **Bluesky**: Implementación personalizada en `bluesky.py`

### Base de Datos
- **Baserow**: Para almacenamiento y gestión de datos

### Herramientas
- **Logging**: Loguru para registro de eventos
- **Configuración**: PyYAML para manejo de configuraciones
- **Procesamiento de imágenes**: Pillow/Pillow-SIMD
- **HTTP**: httpx/requests para solicitudes HTTP
- **Asincronía**: Asyncio para operaciones asíncronas
- **Desarrollo**: VSCode como IDE principal, Pip para gestión de dependencias

## Detalles de Twikit (Twitter)

### Funcionalidades Clave
- Autenticación y manejo de sesión
- Publicación y programación de mensajes
- Distribución de alertas de vuelos interesantes
- Integración con el sistema de monitoreo aéreo

### Características
- Arquitectura asíncrona
- Manejo robusto de errores de API
- Soporte para múltiples tipos de contenido
- Configuración dinámica a través de Telegram

## Detalles de Bluesky

### Implementación
- Código custom en `bluesky.py`
- Uso directo de requests para HTTP
- Sistema de autenticación propio

### Funcionalidades
- Publicación de textos e imágenes
- Soporte para múltiples formatos de contenido
- Manejo de credenciales y tokens

### Ventajas
- Independiente de SDKs externos
- Mayor control sobre la implementación
- Fácil mantenimiento y extensión

## Estructura del Proyecto

### Directorios Principales
- `config/`: Archivos de configuración
- `socials/`: Implementaciones de redes sociales
- `api/`: Integraciones con APIs externas
- `utils/`: Utilidades comunes
- `logs/`: Registros de la aplicación

## Configuraciones Importantes

### Variables de Entorno
- Credenciales de APIs
- Configuraciones de red
- Parámetros de ejecución
- ID de usuario administrador

### Archivos de Configuración
- `config.yaml`: Configuración principal
- `.env`: Variables sensibles

### Configuración a través de Telegram
- Comandos disponibles:
  * /config_redes: Activar/desactivar redes
  * /config_criterios: Modificar criterios de interés
  * /config_intervalo: Cambiar frecuencia de monitoreo
  * /estado: Ver estado actual del sistema
- Validación de permisos por ID de usuario
- Registro de cambios en el sistema
- Confirmación de operaciones exitosas

## Documentación Adicional

### Diagramas
- Arquitectura del sistema
- Flujo de datos
- Proceso de monitoreo aéreo
- Distribución en redes sociales

### Ejemplos de Uso
- Publicación en Twitter
- Integración con Bluesky
- Manejo de errores
- Configuración a través de Telegram

### Consideraciones
- Escalabilidad del sistema
- Seguridad de credenciales
- Manejo de errores y reintentos
- Control de acceso administrativo
- Validación de configuraciones
